"""Dados para o pré-treino por imitação (destilação da heurística).

Gera partidas heurística × heurística em vários processos e grava, para cada decisão com 2+ opções,
(observação codificada, escolha da heurística, resultado final da partida para quem decidiu).
Com probabilidade `epsilon` a jogada EXECUTADA é aleatória, mas o rótulo continua sendo o da heurística:
assim a rede vê estados fora da linha "perfeita" da professora e aprende a se recuperar deles.

Formato (um .npz por shard, só numpy — este módulo não importa torch):
  campos fixos por amostra: slot_ids, slot_tool, slot_feats, hand_ids, glob, ctx_ids, action, value
  descarte esparso: disc_off[N+1], disc_idx, disc_val      (índice em 0..2V-1, valor = contagem/4)
  opções concatenadas: opt_off[N+1], opt_ids, opt_tids, opt_feats
"""
from __future__ import annotations

import json
import os
import random
import time
from multiprocessing import get_context
from pathlib import Path

import numpy as np

from ..encode import GLOB_F, MAX_HAND, N_SLOTS, OPT_F, SLOT_F, V, encode

FIXED = ('slot_ids', 'slot_tool', 'slot_feats', 'hand_ids', 'glob', 'ctx_ids')
FIXED_V2 = ('deck_ids', 'deck_cnt', 'disc_ids', 'disc_cnt', 'slot_x', 'glob2')     # só na observação v2
_DTYPES = {'slot_ids': np.int16, 'slot_tool': np.int16, 'slot_feats': np.float16, 'hand_ids': np.int16,
           'glob': np.float16, 'ctx_ids': np.int16, 'deck_ids': np.int16, 'deck_cnt': np.float16,
           'disc_ids': np.int16, 'disc_cnt': np.float16, 'slot_x': np.float16, 'glob2': np.float16}


def outcome(g, p) -> float:
    return 0.0 if g.winner in (-1, None) else (1.0 if g.winner == p else -1.0)


class ObsPacker:
    """Acumula observações de `encode()` no formato compacto + campos escalares por amostra."""

    def __init__(self):
        self.fixed = {k: [] for k in FIXED}         # + FIXED_V2 quando a primeira observação for v2
        self.disc_idx, self.disc_val, self.disc_len = [], [], []
        self.opt_ids, self.opt_tids, self.opt_feats, self.opt_len = [], [], [], []
        self.scalars: dict = {}

    def __len__(self):
        return len(self.opt_len)

    def add(self, obs, **scalars):
        if not len(self) and 'deck_ids' in obs:
            self.fixed.update({k: [] for k in FIXED_V2})
        for k in self.fixed:
            self.fixed[k].append(obs[k].astype(_DTYPES[k]))
        nz = np.flatnonzero(obs['discard'])
        self.disc_idx.append(nz.astype(np.int16))
        self.disc_val.append(obs['discard'][nz].astype(np.float16))
        self.disc_len.append(len(nz))
        self.opt_ids.append(obs['opt_ids'].astype(np.int16))
        self.opt_tids.append(obs['opt_tids'].astype(np.int16))
        self.opt_feats.append(obs['opt_feats'].astype(np.float16))
        self.opt_len.append(len(obs['opt_ids']))
        for k, v in scalars.items():
            self.scalars.setdefault(k, []).append(v)

    def truncate(self, n):
        """Descarta as amostras a partir da posição n."""
        for lst in (self.disc_len, self.disc_idx, self.disc_val, self.opt_ids, self.opt_tids, self.opt_feats,
                    self.opt_len, *self.fixed.values(), *self.scalars.values()):
            del lst[n:]

    def arrays(self, dtypes=None, **scalars):
        """Dicionário de arrays; `scalars` substitui/acrescenta campos por amostra (listas de tamanho N)."""
        def off(lens):
            return np.concatenate([[0], np.cumsum(lens)]).astype(np.int64)
        out = {k: np.stack(v) for k, v in self.fixed.items()}
        out.update(disc_off=off(self.disc_len), disc_idx=np.concatenate(self.disc_idx),
                   disc_val=np.concatenate(self.disc_val), opt_off=off(self.opt_len),
                   opt_ids=np.concatenate(self.opt_ids), opt_tids=np.concatenate(self.opt_tids),
                   opt_feats=np.concatenate(self.opt_feats))
        dtypes = dtypes or {}
        for k, v in {**self.scalars, **scalars}.items():
            out[k] = np.asarray(v, dtypes.get(k, np.float32))
        return out


def _gen_shard(task):
    """Roda num processo filho: joga `n_games` partidas e grava um shard."""
    from ..agents import HeuristicAgent
    from ..decks import load_deck
    from ..engine import Game
    path, seed, n_games, deck_names, epsilon, max_decisions, versao, professor = task
    rng = random.Random(seed)
    teacher = HeuristicAgent(seed=rng.randrange(2 ** 31))
    if professor != 'heuristic':         # outra professora (ex.: 'nivel:9' = melhor rede, jogada mais provável)
        import torch
        from ..agents import make_agent
        torch.set_num_threads(1)
        teacher = make_agent(professor)
    decks = {}
    w = ObsPacker()
    values = []
    stats = {'games': 0, 'samples': 0, 'draws': 0, 'errors': 0, 'erros': []}
    for k in range(n_games):
        names = (rng.choice(deck_names), rng.choice(deck_names))
        for n in names:
            if n not in decks:
                decks[n] = load_deck(n).cards
        start = len(w)
        try:
            g = Game(decks[names[0]], decks[names[1]], seed=rng.randrange(2 ** 31))
            players = []
            while not g.done and g.decisions < max_decisions:
                pr = g.prompt
                label = teacher.act(g, pr)
                if len(pr.options) > 1:
                    w.add(encode(g, versao=versao), action=label, game=k)
                    players.append(pr.player)
                act = rng.randrange(len(pr.options)) if epsilon and rng.random() < epsilon else label
                g.step(act)
        except Exception as e:
            # partida com erro do motor: descarta as amostras dela e anota para investigar
            import traceback
            tb = traceback.extract_tb(e.__traceback__)[-3:]
            stats['errors'] += 1
            stats['erros'].append({'decks': names, 'erro': f'{type(e).__name__}: {e}'[:300],
                                   'onde': [f'{Path(f.filename).name}:{f.lineno} {f.name}' for f in tb]})
            w.truncate(start)
            continue
        values += [outcome(g, p) for p in players]
        stats['games'] += 1
        stats['draws'] += g.winner in (-1, None)
    stats['samples'] = len(w)
    if len(w):
        np.savez(path, **w.arrays({'action': np.int16, 'game': np.int32}, value=values))
    return stats


def generate(out_dir, n_games, deck_names, epsilon=0.05, workers=None, games_per_shard=100,
             max_decisions=3000, seed=0, log=print, versao=1, professor='heuristic'):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    existing = sorted(out.glob('shard_*.npz'))
    first = len(existing)
    meta_path = out / 'meta.json'
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if meta and meta.get('obs', 1) != versao:
        raise ValueError(f'{out_dir} tem observação v{meta.get("obs", 1)}; use outra pasta para a v{versao}.')
    antes = {r.get('professor', 'heuristic') for r in meta.get('rodadas', [])}
    if antes and antes != {professor}:
        raise ValueError(f'{out_dir} tem partidas da professora {sorted(antes)}; use outra pasta para {professor}.')
    if meta and meta.get('vocab') != V:
        raise ValueError(f'{out_dir} foi gerado com vocabulário {meta.get("vocab")}, o pool atual tem {V}. '
                         'Use outra pasta.')
    meta.update(obs=versao, vocab=V, slot_f=SLOT_F, glob_f=GLOB_F, opt_f=OPT_F, n_slots=N_SLOTS, max_hand=MAX_HAND)
    meta.setdefault('rodadas', []).append({'partidas': n_games, 'epsilon': epsilon, 'decks': deck_names,
                                           'seed': seed, 'professor': professor, 'quando': time.strftime('%Y-%m-%d %H:%M')})
    n_shards = (n_games + games_per_shard - 1) // games_per_shard
    tasks = []
    for s in range(n_shards):
        n = min(games_per_shard, n_games - s * games_per_shard)
        tasks.append((str(out / f'shard_{first + s:05d}.npz'), seed * 1_000_003 + first + s, n, deck_names,
                      epsilon, max_decisions, versao, professor))
    workers = workers or max(1, (os.cpu_count() or 2) - 2)
    if professor != 'heuristic':
        import torch  # noqa: F401  (importar antes do fork: o gancho de import do W&B falha nos filhos)
    t0 = time.perf_counter()
    tot = {'games': 0, 'samples': 0, 'draws': 0, 'errors': 0}
    with get_context('fork').Pool(workers) as pool:
        for i, st in enumerate(pool.imap_unordered(_gen_shard, tasks), 1):
            for k in tot:
                tot[k] += st[k]
            if st['erros']:
                with open(out / 'erros.jsonl', 'a') as f:
                    for e in st['erros']:
                        f.write(json.dumps(e, ensure_ascii=False) + '\n')
            log(f'  shard {i}/{n_shards}: {tot["games"]} partidas, {tot["samples"]} amostras '
                f'({time.perf_counter() - t0:.0f}s)')
    meta_path.write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    if tot['errors']:
        log(f'  {tot["errors"]} partidas com erro do motor (descartadas) — detalhes em {out / "erros.jsonl"}')
    return tot


class PackedObs:
    """Amostras compactas (shards em disco ou partes vindas dos workers do PPO) com montagem de lote vetorizada.

    Campos escalares por amostra (action, value, logp, adv...) vêm junto no lote com o mesmo nome."""
    RAGGED = {'disc': ('disc_idx', 'disc_val'), 'opt': ('opt_ids', 'opt_tids', 'opt_feats')}

    def __init__(self, parts):
        parts = [p for p in parts if len(p['opt_off']) > 1]
        if not parts:
            raise FileNotFoundError('nenhuma amostra')
        n_each = [len(p['opt_off']) - 1 for p in parts]
        ragged_keys = {k for ks in self.RAGGED.values() for k in ks} | {'disc_off', 'opt_off'}
        self.fixed = FIXED + tuple(k for k in FIXED_V2 if k in parts[0])
        self.obs = 2 if 'deck_ids' in parts[0] else 1
        self.scalar_keys = [k for k in parts[0] if k not in ragged_keys and k not in self.fixed
                            and parts[0][k].shape == (n_each[0],)]
        self.d = {k: np.concatenate([p[k] for p in parts]) for k in (*self.fixed, *self.scalar_keys)}
        for pre, keys in self.RAGGED.items():
            offs, base = [], 0
            for p in parts:
                offs.append(p[f'{pre}_off'][:-1] + base)
                base += p[f'{pre}_off'][-1]
            self.d[f'{pre}_off'] = np.concatenate(offs + [np.array([base])])
            for k in keys:
                self.d[k] = np.concatenate([p[k] for p in parts])
        self.n = sum(n_each)

    @classmethod
    def from_paths(cls, paths):
        return cls([dict(np.load(p)) for p in paths])

    @classmethod
    def from_dir(cls, path):
        return cls.from_paths(sorted(Path(path).glob('shard_*.npz')))

    def __len__(self):
        return self.n

    def _ragged(self, pre, idx):
        off = self.d[f'{pre}_off']
        st = off[idx]
        ln = off[idx + 1] - st
        rows = np.repeat(np.arange(len(idx)), ln)
        cols = np.arange(ln.sum()) - np.repeat(np.cumsum(ln) - ln, ln)
        return rows, cols, np.repeat(st, ln) + cols, ln

    def batch(self, idx):
        """Lote em numpy no mesmo formato de `model.collate` (+ os campos escalares)."""
        d, B = self.d, len(idx)
        out = {k: d[k][idx].astype(np.float32 if d[k].dtype == np.float16 else np.int64) for k in self.fixed}
        rows, _, src, _ = self._ragged('disc', idx)
        disc = np.zeros((B, 2 * V), np.float32)
        disc[rows, d['disc_idx'][src].astype(np.int64)] = d['disc_val'][src]
        out['discard'] = disc
        rows, cols, src, ln = self._ragged('opt', idx)
        A = -(-int(ln.max()) // 16) * 16    # múltiplo de 16: menos formatos distintos → menos cache na GPU
        ids = np.zeros((B, A), np.int64)
        tids = np.zeros((B, A), np.int64)
        feats = np.zeros((B, A, OPT_F), np.float32)
        mask = np.zeros((B, A), bool)
        ids[rows, cols] = d['opt_ids'][src]
        tids[rows, cols] = d['opt_tids'][src]
        feats[rows, cols] = d['opt_feats'][src]
        mask[rows, cols] = True
        out.update(opt_ids=ids, opt_tids=tids, opt_feats=feats, opt_mask=mask)
        for k in self.scalar_keys:
            v = d[k][idx]
            out[k] = v.astype(np.int64) if np.issubdtype(v.dtype, np.integer) else v.astype(np.float32)
        return out
