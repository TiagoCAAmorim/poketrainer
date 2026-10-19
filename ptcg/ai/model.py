"""Rede política/valor em PyTorch.

A política não usa um espaço de ações fixo: cada opção legal vira um vetor (carta envolvida,
alvo, tipo de ação...) e a rede dá uma nota para cada uma — o softmax é feito só entre as
opções legais. Isso permite qualquer carta/efeito novo sem mudar a arquitetura.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from ..encode import GLOB_F, OPT_F, PER_SIDE, SLOT_F, V

STATE_KEYS = ('slot_ids', 'slot_tool', 'slot_feats', 'hand_ids', 'discard', 'glob', 'ctx_ids')
NEG = -1e9


def collate(obs_list, device='cpu'):
    out = {k: torch.as_tensor(np.stack([o[k] for o in obs_list])).to(device) for k in STATE_KEYS}
    B = len(obs_list)
    A = max(len(o['opt_ids']) for o in obs_list)
    ids = np.zeros((B, A), np.int64)
    tids = np.zeros((B, A), np.int64)
    feats = np.zeros((B, A, OPT_F), np.float32)
    mask = np.zeros((B, A), bool)
    for i, o in enumerate(obs_list):
        n = len(o['opt_ids'])
        ids[i, :n] = o['opt_ids']
        tids[i, :n] = o['opt_tids']
        feats[i, :n] = o['opt_feats']
        mask[i, :n] = True
    out['opt_ids'] = torch.as_tensor(ids).to(device)
    out['opt_tids'] = torch.as_tensor(tids).to(device)
    out['opt_feats'] = torch.as_tensor(feats).to(device)
    out['opt_mask'] = torch.as_tensor(mask).to(device)
    return out


def _mlp(i, h, o, layers=2):
    mods, d = [], i
    for _ in range(layers - 1):
        mods += [nn.Linear(d, h), nn.ReLU()]
        d = h
    mods += [nn.Linear(d, o), nn.ReLU()]
    return nn.Sequential(*mods)


class PolicyValueNet(nn.Module):
    def __init__(self, vocab: int = V, emb: int = 48, hidden: int = 256):
        super().__init__()
        self.config = dict(vocab=vocab, emb=emb, hidden=hidden)
        H, E = hidden, emb
        self.card = nn.Embedding(vocab, E, padding_idx=0)
        self.slot_mlp = _mlp(2 * E + SLOT_F, H, H)
        self.hand_mlp = _mlp(E, H, H)
        self.disc_mlp = _mlp(2 * vocab, H, H, 1)
        self.glob_mlp = _mlp(GLOB_F, H, H, 1)
        self.trunk = _mlp(4 * H + 3 * H + 2 * E, H, H, 3)
        self.value_head = nn.Sequential(nn.Linear(H, H // 2), nn.ReLU(), nn.Linear(H // 2, 1))
        self.opt_mlp = _mlp(2 * E + OPT_F, H, H)
        self.score = nn.Sequential(nn.Linear(3 * H, H), nn.ReLU(), nn.Linear(H, 1))

    def state(self, b):
        E = self.card
        slots = torch.cat([E(b['slot_ids']), E(b['slot_tool']), b['slot_feats']], -1)    # B,18,*
        sh = self.slot_mlp(slots)                                                        # B,18,H
        present = b['slot_feats'][..., 0:1]                                              # B,18,1

        def bench_mean(x, m):
            return (x * m).sum(1) / m.sum(1).clamp(min=1.0)

        P = PER_SIDE
        my_act, opp_act = sh[:, 0], sh[:, P]
        my_bench = bench_mean(sh[:, 1:P], present[:, 1:P])
        opp_bench = bench_mean(sh[:, P + 1:], present[:, P + 1:])
        hand_mask = (b['hand_ids'] > 0).float().unsqueeze(-1)
        hand = (self.hand_mlp(E(b['hand_ids'])) * hand_mask).sum(1) / 7.0
        disc = self.disc_mlp(b['discard'])
        glob = self.glob_mlp(b['glob'])
        ctx = E(b['ctx_ids']).flatten(1)
        x = torch.cat([my_act, my_bench, opp_act, opp_bench, hand, disc, glob, ctx], -1)
        return self.trunk(x)

    def forward(self, b, detach_value=False):
        """detach_value: a perda de valor não altera o tronco (usado na imitação, onde o valor decora as partidas)."""
        s = self.state(b)                                                                # B,H
        o = torch.cat([self.card(b['opt_ids']), self.card(b['opt_tids']), b['opt_feats']], -1)
        oh = self.opt_mlp(o)                                                             # B,A,H
        se = s.unsqueeze(1).expand_as(oh)
        logits = self.score(torch.cat([se, oh, se * oh], -1)).squeeze(-1)               # B,A
        logits = logits.masked_fill(~b['opt_mask'], NEG)
        value = torch.tanh(self.value_head(s.detach() if detach_value else s).squeeze(-1))
        return logits, value


def save_checkpoint(path, net, extra=None):
    torch.save({'model': net.state_dict(), 'config': net.config, 'extra': extra or {}}, path)


def load_checkpoint(path, device='cpu'):
    ck = torch.load(path, map_location=device, weights_only=False)
    cfg = ck['config']
    if cfg['vocab'] != V:
        raise ValueError(f'Checkpoint treinado com vocabulário {cfg["vocab"]}, pool atual tem {V}. '
                         'Rode expand_vocab ou re-treine após atualizar a base de cartas.')
    net = PolicyValueNet(**cfg)
    net.load_state_dict(ck['model'])
    net.to(device).eval()
    return net, ck.get('extra', {})


def expand_vocab(net: PolicyValueNet, new_vocab: int) -> PolicyValueNet:
    """Cria uma rede com vocabulário maior copiando os pesos (para cartas novas no fim do registro)."""
    cfg = dict(net.config, vocab=new_vocab)
    new = PolicyValueNet(**cfg)
    sd = new.state_dict()
    for k, v in net.state_dict().items():
        if k == 'card.weight':
            sd[k][:v.shape[0]] = v
        elif k == 'disc_mlp.0.weight':
            old = net.config['vocab']
            sd[k][:, :old] = v[:, :old]
            sd[k][:, new_vocab:new_vocab + old] = v[:, old:]
        else:
            sd[k] = v
    new.load_state_dict(sd)
    return new


def masked_entropy(logits, mask):
    logp = F.log_softmax(logits, -1)
    p = logp.exp() * mask
    return -(p * logp.masked_fill(~mask, 0.0)).sum(-1)
