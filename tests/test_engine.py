"""Testes de robustez do motor com os decks reais (top 8 importados): invariantes + determinismo.

Rodar:  python -m pytest -q tests   ou   python tests/test_engine.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ptcg.agents import HeuristicAgent, RandomAgent  # noqa: E402
from ptcg.decks import list_decks, load_deck  # noqa: E402
from ptcg.engine import Game  # noqa: E402
from tests.fuzz import check as check_invariants  # noqa: E402

DECKS = {n: load_deck(n).cards for n in list_decks()}


def run(agent_cls, n_games, seed0=0, check=True):
    names = sorted(DECKS)
    rng = random.Random(seed0)
    results = []
    for k in range(n_games):
        d0, d1 = rng.choice(names), rng.choice(names)
        agents = [agent_cls(seed=k), agent_cls(seed=k + 10000)]
        g = Game(DECKS[d0], DECKS[d1], seed=seed0 + k)
        while not g.done:
            if check:
                check_invariants(g)
            g.step(agents[g.prompt.player].act(g, g.prompt))
        check_invariants(g)
        results.append(g)
    return results


def test_random_games():
    gs = run(RandomAgent, 60)
    assert all(g.done for g in gs)


def test_heuristic_games():
    gs = run(HeuristicAgent, 30, seed0=5000)
    reasons = [g.end_reason for g in gs]
    assert sum('prêmios' in r for r in reasons) > len(gs) * 0.3, reasons


def test_replay_determinism():
    names = sorted(DECKS)
    agents = [RandomAgent(seed=1), RandomAgent(seed=2)]
    g = Game(DECKS[names[0]], DECKS[names[-1]], seed=123)
    for _ in range(150):
        if g.done:
            break
        g.step(agents[g.prompt.player].act(g, g.prompt))
    c = g.clone()
    assert c.history == g.history
    assert [len(p.hand) for p in c.players] == [len(p.hand) for p in g.players]
    assert [x['msg'] for x in c.log] == [x['msg'] for x in g.log]
    if not g.done:
        assert [o.label for o in c.prompt.options] == [o.label for o in g.prompt.options]


if __name__ == '__main__':
    import time
    t = time.time()
    test_random_games()
    test_heuristic_games()
    test_replay_determinism()
    print('ok', round(time.time() - t, 1), 's')
