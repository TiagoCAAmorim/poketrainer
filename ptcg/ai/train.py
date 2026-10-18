"""Treino por self-play com PPO.

    python imitar.py gerar && python imitar.py treinar               # 1º: pré-treino imitando a heurística
    python train.py --resume checkpoints/imitacao.pt --iterations 500

Cada iteração joga `--games` partidas espalhadas por `--workers` processos (rede na CPU, inferência em lote
dentro de cada processo); parte contra a própria rede, parte contra a heurística e parte contra versões
antigas (evita "esquecer" estratégias). A atualização PPO roda na GPU com as transições no formato compacto
de `dataset.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from ..decks import list_decks
from .dataset import ObsPacker, PackedObs
from .model import PolicyValueNet, load_checkpoint, masked_entropy, save_checkpoint


def prize_diff(g, p):
    return g.prizes_taken(p) - g.prizes_taken(1 - p)


# ------------------------------------------------------------------ rollouts (rodam nos workers)
_CACHE: dict = {}


def _net(path):
    """Rede carregada de `path` (na CPU), recarregada só quando o arquivo muda."""
    key = (path, os.stat(path).st_mtime_ns)
    if key not in _CACHE:
        for k in [k for k in _CACHE if k[0] == path]:
            del _CACHE[k]
        _CACHE[key] = load_checkpoint(path, 'cpu')[0]
    return _CACHE[key]


def _deck(name):
    from ..decks import load_deck
    key = ('deck', name)
    if key not in _CACHE:
        _CACHE[key] = load_deck(name).cards
    return _CACHE[key]


def _worker_init():
    torch.set_num_threads(1)


class Rollout:
    def __init__(self, deck_names, rng, a):
        from ..agents import HeuristicAgent, RandomAgent
        self.deck_names, self.rng, self.a = deck_names, rng, a
        self.heur = HeuristicAgent(seed=rng.randrange(10 ** 9))
        self.rand = RandomAgent(seed=rng.randrange(10 ** 9))

    def new_game(self, pool):
        from ..engine import Game
        a, rng = self.a, self.rng
        g = Game(_deck(rng.choice(self.deck_names)), _deck(rng.choice(self.deck_names)),
                 seed=rng.randrange(2 ** 31))
        r = rng.random()
        if r < a['p_heuristic']:
            other = 'heuristic'
        elif r < a['p_heuristic'] + a['p_pool'] and pool:
            other = rng.randrange(len(pool))
        else:
            other = 'learner'
        ctrl = ['learner', other] if rng.random() < 0.5 else [other, 'learner']
        return {'g': g, 'ctrl': ctrl, 'traj': {0: [], 1: []}}

    @torch.no_grad()
    def run(self, net, pool, n_games):
        from ..encode import encode
        from .model import collate
        a = self.a
        packer, results = ObsPacker(), []
        stats = {'errors': 0, 'decisions': 0}
        active = [self.new_game(pool) for _ in range(min(a['parallel'], n_games))]
        started = len(active)
        while active:
            broken = set()
            for gm in active:   # agentes de regra jogam direto
                g = gm['g']
                try:
                    while not g.done and gm['ctrl'][g.prompt.player] in ('heuristic', 'random'):
                        ag = self.heur if gm['ctrl'][g.prompt.player] == 'heuristic' else self.rand
                        g.step(ag.act(g, g.prompt))
                except Exception:
                    broken.add(id(gm))
            groups = {}
            for gm in active:
                g = gm['g']
                if not g.done and id(gm) not in broken:
                    groups.setdefault(gm['ctrl'][g.prompt.player], []).append(gm)
            for key, gms in groups.items():
                model = net if key == 'learner' else pool[key]
                obs = [encode(gm['g']) for gm in gms]
                logits, values = model(collate(obs))
                dist = torch.distributions.Categorical(logits=logits)
                acts = dist.sample()
                logps = dist.log_prob(acts)
                for gm, o, act, lp, v in zip(gms, obs, acts.tolist(), logps.tolist(), values.tolist()):
                    g = gm['g']
                    p = g.prompt.player
                    if key == 'learner' and len(g.prompt.options) > 1:
                        gm['traj'][p].append({'obs': o, 'a': act, 'logp': lp, 'v': v, 'pd': prize_diff(g, p)})
                    try:
                        g.step(act)
                    except Exception:
                        broken.add(id(gm))
            still = []
            for gm in active:
                g = gm['g']
                if id(gm) in broken:
                    stats['errors'] += 1      # erro do motor: a partida é descartada
                elif g.done or g.decisions > a['max_decisions']:
                    stats['decisions'] += g.decisions
                    for p in (0, 1):
                        if gm['ctrl'][p] == 'learner' and gm['traj'][p]:
                            self.finish(gm['traj'][p], g, p, packer)
                    learner = [p for p in (0, 1) if gm['ctrl'][p] == 'learner']
                    other = [c for c in gm['ctrl'] if c != 'learner']
                    if other:
                        lp = learner[0]
                        res = 1 if g.winner == lp else (0 if g.winner in (-1, None) else -1)
                        results.append((other[0] if isinstance(other[0], str) else 'pool', res))
                else:
                    still.append(gm)
                    continue
                if started < n_games:
                    still.append(self.new_game(pool))
                    started += 1
            active = still
        return packer, results, stats

    def finish(self, traj, g, p, packer):
        a = self.a
        final = 0.0 if g.winner in (-1, None) else (1.0 if g.winner == p else -1.0)
        final_pd = prize_diff(g, p)
        T = len(traj)
        for t in range(T):
            nxt = traj[t + 1]['pd'] if t + 1 < T else final_pd
            traj[t]['r'] = a['shaping'] * (nxt - traj[t]['pd']) + (final if t == T - 1 else 0.0)
        adv = 0.0
        for t in reversed(range(T)):
            v_next = traj[t + 1]['v'] if t + 1 < T else 0.0
            delta = traj[t]['r'] + a['gamma'] * v_next - traj[t]['v']
            adv = delta + a['gamma'] * a['lam'] * adv
            traj[t]['adv'] = adv
            traj[t]['ret'] = adv + traj[t]['v']
        for t in traj:
            packer.add(t['obs'], action=t['a'], logp=t['logp'], adv=t['adv'], ret=t['ret'])


def rollout_task(task):
    """Uma fatia das partidas da iteração (roda num worker, ou no processo principal com --workers 0)."""
    learner_path, pool_paths, n_games, seed, deck_names, a = task
    net = _net(learner_path)
    pool = [_net(p) for p in pool_paths]
    packer, results, stats = Rollout(deck_names, random.Random(seed), a).run(net, pool, n_games)
    arrays = packer.arrays({'action': np.int64}) if len(packer) else None
    return arrays, results, stats


# ------------------------------------------------------------------ atualização (GPU)
def ppo_update(net, opt, data: PackedObs, args, device):
    N = len(data)
    adv_all = data.d['adv']
    data.d['adv'] = ((adv_all - adv_all.mean()) / (adv_all.std() + 1e-8)).astype(np.float32)
    stats = {'pi': 0.0, 'v': 0.0, 'ent': 0.0, 'kl': 0.0, 'clip': 0.0, 'n': 0}
    net.train()
    for _ in range(args.epochs):
        idx = np.random.permutation(N)
        for s in range(0, N, args.minibatch):
            b = {k: torch.as_tensor(v).to(device, non_blocking=True)
                 for k, v in data.batch(idx[s:s + args.minibatch]).items()}
            A = b['adv']
            logits, value = net(b)
            logp = F.log_softmax(logits, -1).gather(1, b['action'][:, None]).squeeze(1)
            ratio = torch.exp(logp - b['logp'])
            pi_loss = -torch.min(ratio * A, ratio.clamp(1 - args.clip, 1 + args.clip) * A).mean()
            v_loss = F.mse_loss(value, b['ret'].clamp(-1.5, 1.5))
            ent = masked_entropy(logits, b['opt_mask']).mean()
            loss = pi_loss + args.vf_coef * v_loss - args.ent_coef * ent
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), args.max_grad)
            opt.step()
            stats['pi'] += pi_loss.item()
            stats['v'] += v_loss.item()
            stats['ent'] += ent.item()
            stats['kl'] += (b['logp'] - logp).mean().item()
            stats['clip'] += ((ratio - 1).abs() > args.clip).float().mean().item()
            stats['n'] += 1
    net.eval()
    n = max(stats.pop('n'), 1)
    return {k: v / n for k, v in stats.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description='Treino PPO self-play para o simulador de Pokémon TCG')
    ap.add_argument('--decks', nargs='+', default=None, help='padrão: todos os decks em decks/')
    ap.add_argument('--pasta', default=None, help='subpasta de decks/ (ex.: tests)')
    ap.add_argument('--iterations', type=int, default=300)
    ap.add_argument('--games', type=int, default=240, help='partidas por iteração')
    ap.add_argument('--workers', type=int, default=None, help='processos de rollout (0 = no processo principal)')
    ap.add_argument('--parallel', type=int, default=8, help='partidas simultâneas por worker (lote de inferência)')
    ap.add_argument('--epochs', type=int, default=3)
    ap.add_argument('--minibatch', type=int, default=1024)
    ap.add_argument('--lr', type=float, default=1e-4)
    ap.add_argument('--gamma', type=float, default=0.997)
    ap.add_argument('--lam', type=float, default=0.95)
    ap.add_argument('--clip', type=float, default=0.2)
    ap.add_argument('--vf-coef', type=float, default=0.5)
    ap.add_argument('--ent-coef', type=float, default=0.005)
    ap.add_argument('--max-grad', type=float, default=0.5)
    ap.add_argument('--shaping', type=float, default=0.05, help='recompensa por prêmio de vantagem')
    ap.add_argument('--p-heuristic', type=float, default=0.25)
    ap.add_argument('--p-pool', type=float, default=0.15)
    ap.add_argument('--pool-size', type=int, default=5)
    ap.add_argument('--snapshot-every', type=int, default=20)
    ap.add_argument('--eval-every', type=int, default=10)
    ap.add_argument('--eval-games', type=int, default=200)
    ap.add_argument('--max-decisions', type=int, default=3000)
    ap.add_argument('--hidden', type=int, default=256)
    ap.add_argument('--emb', type=int, default=48)
    ap.add_argument('--out', default='checkpoints')
    ap.add_argument('--resume', default=None, help='ex.: checkpoints/imitacao.pt')
    ap.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)

    from .imitate import evaluate_parallel
    out = Path(args.out)
    (out / '_pool').mkdir(parents=True, exist_ok=True)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    rng = random.Random(args.seed)
    deck_names = args.decks or (list_decks(args.pasta) if args.pasta else list_decks())
    if args.resume:
        net, _ = load_checkpoint(args.resume, args.device)
    else:
        net = PolicyValueNet(emb=args.emb, hidden=args.hidden).to(args.device)
    net.eval()
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    workers = args.workers if args.workers is not None else max(1, (os.cpu_count() or 2) - 2)
    roll_cfg = dict(gamma=args.gamma, lam=args.lam, shaping=args.shaping, p_heuristic=args.p_heuristic,
                    p_pool=args.p_pool, parallel=args.parallel, max_decisions=args.max_decisions)
    learner_path = str(out / '_pool' / 'learner.pt')
    pool_paths: list = []
    best = -1.0
    log_path = out / 'train_log.jsonl'
    print(f'Treinando em {args.device} com {len(deck_names)} decks, {workers} workers'
          + (f', partindo de {args.resume}' if args.resume else ''))
    executor = get_context('spawn').Pool(workers, initializer=_worker_init) if workers else None
    try:
        if args.resume and args.eval_games:
            r = evaluate_parallel(net, deck_names, args.eval_games, workers=workers, pool=executor)
            best = r['vitorias']
            print(json.dumps({'it': 0, 'eval_vs_heuristica': r}, ensure_ascii=False), flush=True)
        for it in range(1, args.iterations + 1):
            t0 = time.perf_counter()
            save_checkpoint(learner_path, net)
            n = max(workers, 1)
            sizes = [args.games // n + (1 if k < args.games % n else 0) for k in range(n)]
            tasks = [(learner_path, list(pool_paths), sz, rng.randrange(2 ** 31), deck_names, roll_cfg)
                     for sz in sizes if sz]
            outs = executor.map(rollout_task, tasks) if executor else [rollout_task(t) for t in tasks]
            parts = [o[0] for o in outs if o[0] is not None]
            results = [r for o in outs for r in o[1]]
            errors = sum(o[2]['errors'] for o in outs)
            t1 = time.perf_counter()
            data = PackedObs(parts)
            st = ppo_update(net, opt, data, args, args.device)
            rec = {'it': it, 'transicoes': len(data), 'rollout_s': round(t1 - t0, 1),
                   'update_s': round(time.perf_counter() - t1, 1), **{k: round(v, 4) for k, v in st.items()}}
            if errors:
                rec['erros_motor'] = errors
            vs_h = [r for o, r in results if o == 'heuristic']
            if vs_h:
                rec['treino_vs_heuristica'] = round((np.mean(vs_h) + 1) / 2, 3)
            if it % args.snapshot_every == 0:
                snap = str(out / '_pool' / f'snap_{it:05d}.pt')
                save_checkpoint(snap, net, {'it': it})
                pool_paths.append(snap)
                for old in pool_paths[:-args.pool_size]:
                    os.remove(old)
                pool_paths[:] = pool_paths[-args.pool_size:]
            if it % args.eval_every == 0:
                r = evaluate_parallel(net, deck_names, args.eval_games, workers=workers, pool=executor)
                rec['eval_vs_heuristica'] = r['vitorias']
                save_checkpoint(str(out / 'latest.pt'), net, {'it': it, 'decks': deck_names})
                if r['vitorias'] > best:
                    best = r['vitorias']
                    save_checkpoint(str(out / 'best.pt'), net, {'it': it, 'winrate': best, 'decks': deck_names})
            print(json.dumps(rec, ensure_ascii=False), flush=True)
            with open(log_path, 'a') as f:
                f.write(json.dumps(rec) + '\n')
    finally:
        if executor:
            executor.close()
            executor.join()
    save_checkpoint(str(out / 'latest.pt'), net, {'it': args.iterations, 'decks': deck_names})


if __name__ == '__main__':
    main()
