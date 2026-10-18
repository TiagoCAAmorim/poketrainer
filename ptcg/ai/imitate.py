"""Pré-treino por imitação da heurística + avaliação paralela contra agentes de referência.

O checkpoint gerado aqui é o ponto de partida do PPO:  python train.py --resume checkpoints/imitacao.pt
"""
from __future__ import annotations

import json
import math
import os
import random
import time
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from .dataset import PackedObs
from .model import PolicyValueNet, load_checkpoint, save_checkpoint


def to_device(b, device):
    return {k: torch.as_tensor(v).to(device, non_blocking=True) for k, v in b.items()}


def split_shards(data_dir, val_every=20):
    paths = sorted(Path(data_dir).glob('shard_*.npz'))
    if len(paths) < 2:
        return paths, []
    val = paths[::val_every] if len(paths) >= val_every else paths[-1:]
    return [p for p in paths if p not in val], val


@torch.no_grad()
def val_metrics(net, data, device, batch=2048, limit=200_000):
    net.eval()
    n = min(len(data), limit)
    tot = {'loss_pi': 0.0, 'acc': 0.0, 'mse_v': 0.0}
    for s in range(0, n, batch):
        idx = np.arange(s, min(s + batch, n))
        b = to_device(data.batch(idx), device)
        logits, value = net(b)
        tot['loss_pi'] += F.cross_entropy(logits, b['action'], reduction='sum').item()
        tot['acc'] += (logits.argmax(-1) == b['action']).sum().item()
        tot['mse_v'] += F.mse_loss(value, b['value'], reduction='sum').item()
    return {k: v / n for k, v in tot.items()}


def train_imitation(data_dir, out, epochs=8, batch=1024, lr=1e-3, weight_decay=1e-4, vf_coef=0.25,
                    hidden=256, emb=48, resume=None, device=None, seed=0, eval_games=0, detach_value=True,
                    log=print, wb=None):
    """wb: execução do W&B (`ptcg.ai.wb.start`) para registrar as métricas; None = não registra."""
    device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    tr_paths, va_paths = split_shards(data_dir)
    t0 = time.perf_counter()
    train = PackedObs.from_paths(tr_paths)
    val = PackedObs.from_paths(va_paths) if va_paths else None
    log(f'Dados: {len(train)} amostras de treino, {len(val) if val else 0} de validação '
        f'({len(tr_paths)}+{len(va_paths)} shards, {time.perf_counter() - t0:.0f}s para carregar)')
    if resume:
        net, _ = load_checkpoint(resume, device)
    else:
        net = PolicyValueNet(emb=emb, hidden=hidden).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=weight_decay)
    steps = epochs * math.ceil(len(train) / batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.05)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    log_path = Path(out).with_suffix('.jsonl')
    best, best_rec = None, None
    gstep = 0
    for ep in range(1, epochs + 1):
        net.train()
        perm = rng.permutation(len(train))
        agg = {'loss_pi': 0.0, 'acc': 0.0, 'mse_v': 0.0, 'n': 0}
        t0 = time.perf_counter()
        for s in range(0, len(perm), batch):
            b = to_device(train.batch(perm[s:s + batch]), device)
            logits, value = net(b, detach_value=detach_value)
            loss_pi = F.cross_entropy(logits, b['action'])
            mse_v = F.mse_loss(value, b['value'])
            loss = loss_pi + vf_coef * mse_v
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            sched.step()
            k = len(b['action'])
            agg['loss_pi'] += loss_pi.item() * k
            agg['mse_v'] += mse_v.item() * k
            agg['acc'] += (logits.argmax(-1) == b['action']).float().sum().item()
            agg['n'] += k
            step = s // batch + 1
            gstep += 1
            if step % 500 == 0:      # progresso dentro da época (detecta GPU lenta/sem memória cedo)
                el = time.perf_counter() - t0
                log(f'  época {ep}: {agg["n"]}/{len(perm)} amostras, {step / el:.1f} passos/s, '
                    f'acerto {agg["acc"] / agg["n"]:.3f}')
                if wb:
                    wb.log({'treino/loss_pi': loss_pi.item(), 'treino/mse_v': mse_v.item(),
                            'treino/acc_parcial': agg['acc'] / agg['n'], 'treino/passos_s': step / el,
                            'treino/lr': sched.get_last_lr()[0], 'epoca': ep - 1 + agg['n'] / len(perm)},
                           step=gstep)
        n = agg.pop('n')
        rec = {'epoca': ep, 's': round(time.perf_counter() - t0, 1), **{f'treino_{k}': round(v / n, 4) for k, v in agg.items()}}
        if val is not None:
            rec.update({f'val_{k}': round(v, 4) for k, v in val_metrics(net, val, device).items()})
        net.eval()
        key = rec.get('val_loss_pi', rec['treino_loss_pi'])
        extra = {'fonte': 'imitacao', 'epoca': ep, 'dados': str(data_dir), **rec}
        save_checkpoint(str(Path(out).with_name(Path(out).stem + '_ultimo.pt')), net, extra)
        if best is None or key < best:
            best, best_rec = key, rec
            save_checkpoint(out, net, extra)
        log(json.dumps(rec, ensure_ascii=False))
        if wb:
            wb.log({'epoca': ep, **{('val/' + k[4:] if k.startswith('val_') else 'epoca/' + k): v
                                    for k, v in rec.items() if k != 'epoca'}}, step=gstep)
        with open(log_path, 'a') as f:
            f.write(json.dumps(rec) + '\n')
    if eval_games:
        best_net, _ = load_checkpoint(out, 'cpu')
        meta = Path(data_dir) / 'meta.json'
        decks = sorted({d for r in json.loads(meta.read_text())['rodadas'] for d in r['decks']}) if meta.exists() else None
        r, por_deck = evaluate_parallel(best_net, decks, n_games=eval_games, detalhes=True)
        log(f'Avaliação de {out}: {r}')
        if wb:
            wb.log({'aval/vitorias': r['vitorias'], 'aval/erro_padrao': r['erro_padrao']}, step=gstep)
            wb.table('aval/por_deck', ['deck', 'partidas', 'vitorias'],
                     [[d, len(v), float(np.mean(v))] for d, v in sorted(por_deck.items())])
    else:
        r = None
    resumo = {'checkpoint': str(out), 'dados': str(data_dir), 'amostras_treino': len(train),
              'amostras_val': len(val) if val else 0, 'epocas': epochs, 'lr': lr, 'lote': batch, 'vf_coef': vf_coef,
              'detach_value': detach_value, 'hidden': net.config['hidden'], 'emb': net.config['emb'],
              'melhor_epoca': best_rec, 'avaliacao': r}
    return net, resumo


# ------------------------------------------------------------------ avaliação paralela (CPU)
def _eval_worker(task):
    import torch as T
    from ..agents import HeuristicAgent, RandomAgent
    from ..decks import load_deck
    from ..encode import encode
    from ..engine import Game
    from .model import PolicyValueNet, collate
    T.set_num_threads(1)
    cfg, state, games, deck_names, opponent, max_decisions = task
    net = PolicyValueNet(**cfg)
    net.load_state_dict(state)
    net.eval()
    decks = {}
    res = []
    for seed, me in games:
        rng = random.Random(seed)
        names = (rng.choice(deck_names), rng.choice(deck_names))
        for n in names:
            if n not in decks:
                decks[n] = load_deck(n).cards
        opp = HeuristicAgent(seed=seed) if opponent == 'heuristic' else RandomAgent(seed=seed)
        g = Game(decks[names[0]], decks[names[1]], seed=rng.randrange(2 ** 31))
        with T.no_grad():
            while not g.done and g.decisions < max_decisions:
                if g.prompt.player == me:
                    logits, _ = net(collate([encode(g)]))
                    g.step(int(logits[0].argmax()))
                else:
                    g.step(opp.act(g, g.prompt))
        score = 1.0 if g.winner == me else (0.5 if g.winner in (-1, None) else 0.0)
        res.append({'deck': names[me], 'vs': names[1 - me], 'score': score, 'primeiro': g.first_player == me})
    return res


def evaluate_parallel(net, deck_names=None, n_games=200, opponent='heuristic', workers=None, seed=12345,
                      max_decisions=3000, log=None, pool=None, detalhes=False):
    """Taxa de vitória (empate = ½) da rede, jogando de forma gulosa, contra a heurística ou o aleatório.

    Cada partida é sorteada pela semente, então duas avaliações com a mesma `seed` usam os mesmos confrontos.
    detalhes=True devolve (resumo, {deck: [pontos por partida]})."""
    from ..decks import list_decks
    deck_names = deck_names or list_decks()
    workers = workers or max(1, min((os.cpu_count() or 2) - 2, n_games))
    games = [(seed + k, k % 2) for k in range(n_games)]
    state = {k: v.detach().cpu() for k, v in net.state_dict().items()}
    chunks = [games[i::workers] for i in range(workers)]
    tasks = [(net.config, state, c, deck_names, opponent, max_decisions) for c in chunks if c]
    t0 = time.perf_counter()
    if pool is not None:      # reaproveita um pool já aberto (ex.: o dos rollouts do PPO)
        res = [r for part in pool.map(_eval_worker, tasks) for r in part]
    else:
        with get_context('spawn').Pool(len(tasks)) as own:
            res = [r for part in own.map(_eval_worker, tasks) for r in part]
    wr = float(np.mean([r['score'] for r in res]))
    first = [r['score'] for r in res if r['primeiro']]
    out = {'oponente': opponent, 'partidas': len(res), 'vitorias': round(wr, 3),
           'indo_primeiro': round(float(np.mean(first)), 3) if first else None,
           'erro_padrao': round(float(np.std([r['score'] for r in res]) / math.sqrt(len(res))), 3),
           's': round(time.perf_counter() - t0, 1)}
    by_deck = {}
    for r in res:
        by_deck.setdefault(r['deck'], []).append(r['score'])
    if log:
        for d, v in sorted(by_deck.items(), key=lambda x: -np.mean(x[1])):
            log(f'  {np.mean(v):5.2f}  ({len(v):3d})  {d}')
    return (out, by_deck) if detalhes else out
