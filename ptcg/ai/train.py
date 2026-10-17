"""Treino por self-play com PPO.

    python train.py --decks charizard_pidgeot raging_bolt_ogerpon dragapult --iterations 500

Cada iteração joga N partidas em paralelo (inferência em lote), parte contra a própria rede,
parte contra o agente heurístico e parte contra versões antigas (evita "esquecer" estratégias).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import time

import numpy as np
import torch
import torch.nn.functional as F

from ..agents import HeuristicAgent, RandomAgent
from ..decks import list_decks, load_deck
from ..encode import encode
from ..engine import Game
from .model import PolicyValueNet, collate, load_checkpoint, masked_entropy, save_checkpoint


def prize_diff(g, p):
    return g.prizes_taken(p) - g.prizes_taken(1 - p)


class Rollout:
    def __init__(self, decks, rng, args, device):
        self.decks, self.rng, self.args, self.device = decks, rng, args, device
        self.heur = HeuristicAgent(seed=rng.randrange(10 ** 9))
        self.rand = RandomAgent(seed=rng.randrange(10 ** 9))

    def new_game(self, pool):
        a, rng = self.args, self.rng
        g = Game(rng.choice(self.decks), rng.choice(self.decks), seed=rng.randrange(2 ** 31))
        r = rng.random()
        if r < a.p_heuristic:
            other = 'heuristic'
        elif r < a.p_heuristic + a.p_pool and pool:
            other = rng.randrange(len(pool))
        else:
            other = 'learner'
        ctrl = ['learner', other] if rng.random() < 0.5 else [other, 'learner']
        return {'g': g, 'ctrl': ctrl, 'traj': {0: [], 1: []}}

    @torch.no_grad()
    def run(self, net, pool, n_games):
        a = self.args
        transitions, results = [], []
        active = [self.new_game(pool) for _ in range(min(a.parallel, n_games))]
        started = len(active)
        while active:
            for gm in active:   # agentes de regra jogam direto
                g = gm['g']
                while not g.done and gm['ctrl'][g.prompt.player] in ('heuristic', 'random'):
                    ag = self.heur if gm['ctrl'][g.prompt.player] == 'heuristic' else self.rand
                    g.step(ag.act(g, g.prompt))
            groups = {}
            for gm in active:
                g = gm['g']
                if not g.done:
                    groups.setdefault(gm['ctrl'][g.prompt.player], []).append(gm)
            for key, gms in groups.items():
                model = net if key == 'learner' else pool[key]
                obs = [encode(gm['g']) for gm in gms]
                logits, values = model(collate(obs, self.device))
                dist = torch.distributions.Categorical(logits=logits)
                acts = dist.sample()
                logps = dist.log_prob(acts)
                for gm, o, act, lp, v in zip(gms, obs, acts.tolist(), logps.tolist(), values.tolist()):
                    g = gm['g']
                    p = g.prompt.player
                    if key == 'learner':
                        gm['traj'][p].append({'obs': o, 'a': act, 'logp': lp, 'v': v, 'pd': prize_diff(g, p)})
                    g.step(act)
            still = []
            for gm in active:
                g = gm['g']
                if g.done or g.decisions > a.max_decisions:
                    for p in (0, 1):
                        if gm['ctrl'][p] == 'learner' and gm['traj'][p]:
                            transitions += self.finish(gm['traj'][p], g, p)
                    learner = [p for p in (0, 1) if gm['ctrl'][p] == 'learner']
                    other = [c for c in gm['ctrl'] if c != 'learner']
                    if other:
                        lp = learner[0]
                        res = 1 if g.winner == lp else (0 if g.winner in (-1, None) else -1)
                        results.append((str(other[0]) if isinstance(other[0], str) else 'pool', res))
                    if started < n_games:
                        still.append(self.new_game(pool))
                        started += 1
                else:
                    still.append(gm)
            active = still
        return transitions, results

    def finish(self, traj, g, p):
        a = self.args
        final = 0.0 if g.winner in (-1, None) else (1.0 if g.winner == p else -1.0)
        final_pd = prize_diff(g, p)
        T = len(traj)
        for t in range(T):
            nxt = traj[t + 1]['pd'] if t + 1 < T else final_pd
            traj[t]['r'] = a.shaping * (nxt - traj[t]['pd']) + (final if t == T - 1 else 0.0)
        adv = 0.0
        for t in reversed(range(T)):
            v_next = traj[t + 1]['v'] if t + 1 < T else 0.0
            delta = traj[t]['r'] + a.gamma * v_next - traj[t]['v']
            adv = delta + a.gamma * a.lam * adv
            traj[t]['adv'] = adv
            traj[t]['ret'] = adv + traj[t]['v']
        return traj


def ppo_update(net, opt, data, args, device):
    N = len(data)
    adv = np.array([d['adv'] for d in data], np.float32)
    adv = (adv - adv.mean()) / (adv.std() + 1e-8)
    stats = {'pi': 0.0, 'v': 0.0, 'ent': 0.0, 'kl': 0.0, 'n': 0}
    net.train()
    for _ in range(args.epochs):
        idx = np.random.permutation(N)
        for s in range(0, N, args.minibatch):
            mb = idx[s:s + args.minibatch]
            b = collate([data[i]['obs'] for i in mb], device)
            act = torch.as_tensor([data[i]['a'] for i in mb], device=device)
            old = torch.as_tensor([data[i]['logp'] for i in mb], device=device)
            ret = torch.as_tensor([data[i]['ret'] for i in mb], device=device, dtype=torch.float32)
            A = torch.as_tensor(adv[mb], device=device)
            logits, value = net(b)
            logp_all = F.log_softmax(logits, -1)
            logp = logp_all.gather(1, act[:, None]).squeeze(1)
            ratio = torch.exp(logp - old)
            pi_loss = -torch.min(ratio * A, ratio.clamp(1 - args.clip, 1 + args.clip) * A).mean()
            v_loss = F.mse_loss(value, ret.clamp(-1.5, 1.5))
            ent = masked_entropy(logits, b['opt_mask']).mean()
            loss = pi_loss + args.vf_coef * v_loss - args.ent_coef * ent
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), args.max_grad)
            opt.step()
            stats['pi'] += pi_loss.item()
            stats['v'] += v_loss.item()
            stats['ent'] += ent.item()
            stats['kl'] += (old - logp).mean().item()
            stats['n'] += 1
    net.eval()
    n = max(stats.pop('n'), 1)
    return {k: v / n for k, v in stats.items()}


@torch.no_grad()
def evaluate(net, decks, n_games, device, opponent='heuristic', seed=0):
    rng = random.Random(seed)
    opp = HeuristicAgent(seed=seed) if opponent == 'heuristic' else RandomAgent(seed=seed)
    wins = 0
    for k in range(n_games):
        g = Game(rng.choice(decks), rng.choice(decks), seed=rng.randrange(2 ** 31))
        me = k % 2
        while not g.done and g.decisions < 5000:
            if g.prompt.player == me:
                logits, _ = net(collate([encode(g)], device))
                g.step(int(logits[0].argmax()))
            else:
                g.step(opp.act(g, g.prompt))
        wins += 1.0 if g.winner == me else (0.5 if g.winner == -1 else 0.0)
    return wins / n_games


def main(argv=None):
    ap = argparse.ArgumentParser(description='Treino PPO self-play para o simulador de Pokémon TCG')
    ap.add_argument('--decks', nargs='+', default=None, help='padrão: todos os decks em decks/')
    ap.add_argument('--iterations', type=int, default=300)
    ap.add_argument('--games', type=int, default=64, help='partidas por iteração')
    ap.add_argument('--parallel', type=int, default=32, help='partidas simultâneas (lote de inferência)')
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--minibatch', type=int, default=512)
    ap.add_argument('--lr', type=float, default=3e-4)
    ap.add_argument('--gamma', type=float, default=0.997)
    ap.add_argument('--lam', type=float, default=0.95)
    ap.add_argument('--clip', type=float, default=0.2)
    ap.add_argument('--vf-coef', type=float, default=0.5)
    ap.add_argument('--ent-coef', type=float, default=0.01)
    ap.add_argument('--max-grad', type=float, default=0.5)
    ap.add_argument('--shaping', type=float, default=0.05, help='recompensa por prêmio de vantagem')
    ap.add_argument('--p-heuristic', type=float, default=0.25)
    ap.add_argument('--p-pool', type=float, default=0.15)
    ap.add_argument('--pool-size', type=int, default=5)
    ap.add_argument('--snapshot-every', type=int, default=20)
    ap.add_argument('--eval-every', type=int, default=10)
    ap.add_argument('--eval-games', type=int, default=40)
    ap.add_argument('--max-decisions', type=int, default=3000)
    ap.add_argument('--hidden', type=int, default=256)
    ap.add_argument('--emb', type=int, default=48)
    ap.add_argument('--out', default='checkpoints')
    ap.add_argument('--resume', default=None)
    ap.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    rng = random.Random(args.seed)
    args.decks = args.decks or list_decks()
    decks = [load_deck(n).cards for n in args.decks]
    if args.resume:
        net, _ = load_checkpoint(args.resume, args.device)
    else:
        net = PolicyValueNet(emb=args.emb, hidden=args.hidden).to(args.device)
    net.eval()
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    pool: list = []
    roll = Rollout(decks, rng, args, args.device)
    best = -1.0
    log_path = os.path.join(args.out, 'train_log.jsonl')
    print(f'Treinando em {args.device} com decks {args.decks}')
    for it in range(1, args.iterations + 1):
        t0 = time.time()
        data, results = roll.run(net, pool, args.games)
        t1 = time.time()
        st = ppo_update(net, opt, data, args, args.device)
        rec = {'it': it, 'transitions': len(data), 'rollout_s': round(t1 - t0, 1),
               'update_s': round(time.time() - t1, 1), **{k: round(v, 4) for k, v in st.items()}}
        vs_h = [r for o, r in results if o == 'heuristic']
        if vs_h:
            rec['train_vs_heuristic'] = round((np.mean(vs_h) + 1) / 2, 3)
        if it % args.snapshot_every == 0:
            snap = copy.deepcopy(net).eval()
            pool.append(snap)
            pool[:] = pool[-args.pool_size:]
        if it % args.eval_every == 0:
            wr = evaluate(net, decks, args.eval_games, args.device, 'heuristic', seed=it)
            rec['eval_vs_heuristic'] = wr
            save_checkpoint(os.path.join(args.out, 'latest.pt'), net, {'it': it, 'decks': args.decks})
            if wr > best:
                best = wr
                save_checkpoint(os.path.join(args.out, 'best.pt'), net, {'it': it, 'winrate': wr,
                                                                         'decks': args.decks})
        print(json.dumps(rec, ensure_ascii=False))
        with open(log_path, 'a') as f:
            f.write(json.dumps(rec) + '\n')
    save_checkpoint(os.path.join(args.out, 'latest.pt'), net, {'it': args.iterations, 'decks': args.decks})


if __name__ == '__main__':
    main()
