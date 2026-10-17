"""Execução em lote de partidas (multiprocessing) para testes de deck."""
from __future__ import annotations

import math
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from .agents import make_agent, play_game

_AGENT_CACHE: dict = {}


def _agent(spec, seed):
    if spec.startswith('model:'):          # rede: carrega uma vez por processo
        if spec not in _AGENT_CACHE:
            _AGENT_CACHE[spec] = make_agent(spec)
        return _AGENT_CACHE[spec]
    return make_agent(spec, seed=seed)


def _play_one(job):
    deck_a, deck_b, spec_a, spec_b, seed, a_seat, keep = job
    if a_seat == 0:
        decks, specs = (deck_a, deck_b), (spec_a, spec_b)
    else:
        decks, specs = (deck_b, deck_a), (spec_b, spec_a)
    agents = [_agent(specs[0], seed * 2 + 1), _agent(specs[1], seed * 2 + 2)]
    g = play_game(decks[0], decks[1], agents, seed=seed)
    w = g.winner
    res = 0.5 if w == -1 else (1.0 if w == a_seat else 0.0)
    out = {'res': res, 'turns': g.turn, 'a_first': g.first_player == a_seat, 'reason': g.end_reason,
           'prizes_a': g.prizes_taken(a_seat), 'prizes_b': g.prizes_taken(1 - a_seat)}
    if keep:
        from .logbook import partida_registro
        out['rec'] = partida_registro(g, agentes=list(specs), deck_a_no_assento=a_seat)
    return out


def run_matchup(deck_a, deck_b, n_games, spec_a='heuristic', spec_b='heuristic', seed0=0, workers=None,
                log_session=None, labels=None):
    """Joga n_games alternando assentos. Retorna dict com taxa de vitória do deck A.

    log_session: ptcg.logbook.SessaoSimulacao — grava cada partida (reproduzível) em logs/simulacoes/."""
    keep = log_session is not None
    jobs = [(deck_a, deck_b, spec_a, spec_b, seed0 + i, i % 2, keep) for i in range(n_games)]
    workers = workers if workers is not None else max(1, (os.cpu_count() or 2) - 1)
    if workers <= 1 or n_games < 8:
        out = [_play_one(j) for j in jobs]
    else:
        with ProcessPoolExecutor(workers) as ex:
            out = list(ex.map(_play_one, jobs, chunksize=max(1, n_games // (workers * 4))))
    if keep:
        for o in out:
            rec = o.pop('rec')
            if labels:
                rec['decks'] = list(labels) if rec['deck_a_no_assento'] == 0 else list(labels)[::-1]
            log_session.gravar_registro(rec)
    return summarize(out)


def summarize(out):
    n = len(out)
    wr = sum(o['res'] for o in out) / n
    se = math.sqrt(max(wr * (1 - wr), 1e-9) / n)
    first = [o['res'] for o in out if o['a_first']]
    second = [o['res'] for o in out if not o['a_first']]
    return {
        'games': n, 'winrate': wr, 'ci95': 1.96 * se,
        'wr_going_first': sum(first) / len(first) if first else float('nan'),
        'wr_going_second': sum(second) / len(second) if second else float('nan'),
        'avg_turns': sum(o['turns'] for o in out) / n,
        'avg_prizes_a': sum(o['prizes_a'] for o in out) / n,
        'avg_prizes_b': sum(o['prizes_b'] for o in out) / n,
        'reasons': dict(Counter(o['reason'] for o in out)),
        'raw': [o['res'] for o in out],
    }
