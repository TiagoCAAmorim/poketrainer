"""Teste de estresse do motor: partidas com decks aleatórios legais e jogadas aleatórias.

Checa a cada decisão: 60 cartas por jogador contabilizadas, nenhuma duplicada, nenhum Pokémon
com dano letal na fase principal. Erros são agrupados pela última carta envolvida.

    python tests/fuzz.py --games 300
"""
import argparse
import collections
import os
import random
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ptcg.decks import random_deck  # noqa: E402
from ptcg.engine import Game  # noqa: E402


def check(g):
    uids = []
    for i, pl in enumerate(g.players):
        n = pl.total_cards(g.stadium)
        assert n == 60, f'jogador {i}: {n} cartas contabilizadas'
        for z in pl.zones().values():
            uids += [c.uid for c in z]
        for s in pl.in_play():
            uids += [c.uid for c in s.all_cards()]
            if not g.done and g.prompt is not None and g.prompt.hint == 'main':
                assert s.damage < g.hp(s), f'{s.name} deveria ter sido nocauteado'
        if not g.done and g.prompt is not None and g.prompt.hint == 'main':
            assert len(pl.bench) <= g.bench_max(i), 'banco acima do limite'
    if g.stadium:
        uids.append(g.stadium.uid)
    assert len(uids) == len(set(uids)) == 120, 'carta duplicada/perdida'


def pick(rng, pr):
    """Aleatório enviesado: ataca bastante e evita passar o turno, para exercitar efeitos."""
    opts = pr.options
    if pr.hint == 'main':
        atk = [i for i, o in enumerate(opts) if o.kind == 'attack']
        other = [i for i, o in enumerate(opts) if o.kind not in ('attack', 'end')]
        r = rng.random()
        if atk and r < 0.35:
            return rng.choice(atk)
        if other and r < 0.9:
            return rng.choice(other)
        if atk:
            return rng.choice(atk)
    return rng.randrange(len(opts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--games', type=int, default=200)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args()
    rng = random.Random(a.seed)
    errors = collections.Counter()
    examples = {}
    ends = collections.Counter()
    turns = []
    for k in range(a.games):
        d0, d1 = random_deck(rng), random_deck(rng)
        g = None
        try:
            g = Game(d0, d1, seed=rng.randrange(2 ** 31))
            while not g.done:
                check(g)
                if g.decisions > 4000:
                    raise RuntimeError('partida longa demais (>4000 decisões)')
                g.step(pick(rng, g.prompt))
            check(g)
            ends[g.end_reason.split(' ')[0]] += 1
            turns.append(g.turn)
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)
            where = next((f'{f.filename.split("ptcg/")[-1]}:{f.lineno} {f.name}' for f in reversed(tb)
                          if 'ptcg/' in f.filename), '?')
            key = f'{type(e).__name__}: {str(e)[:90]} @ {where}'
            errors[key] += 1
            if key not in examples:
                last = [x['msg'] for x in (g.log[-6:] if g else [])]
                examples[key] = (last, traceback.format_exc() if a.verbose else '')
    print(f'{a.games} partidas, {sum(errors.values())} com erro; fins: {dict(ends)}; '
          f'turnos médios {sum(turns) / max(1, len(turns)):.1f}')
    for key, n in errors.most_common():
        print(f'\n[{n}x] {key}')
        last, tb = examples[key]
        for m in last:
            print('    |', m)
        if tb:
            print(tb)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
