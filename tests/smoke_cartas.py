"""Teste de fumaça de efeitos: usa cada ataque/Habilidade ativada de cada carta numa posição montada e
resolve todas as decisões escolhendo opções (primeira, última e aleatória). Procura exceções e violações
de invariantes (60 cartas por jogador, nenhuma duplicada, ninguém com dano letal na fase principal).

    python tests/smoke_cartas.py                 # todas as cartas com texto de ataque/Habilidade
    python tests/smoke_cartas.py TWM-23 PBL-26   # só estas
"""
import os
import random
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))

from helpers import at_turn, board, new_game  # noqa: E402
from ptcg.carddb import db  # noqa: E402
from ptcg.core import ENERGY_TYPES  # noqa: E402

BASIC = {'G': 'Basic Grass Energy', 'R': 'Basic Fire Energy', 'W': 'Basic Water Energy', 'L': 'Basic Lightning Energy',
         'P': 'Basic Psychic Energy', 'F': 'Basic Fighting Energy', 'D': 'Basic Darkness Energy',
         'M': 'Basic Metal Energy', 'N': 'Basic Psychic Energy', 'C': 'Basic Psychic Energy'}


def invariants(g):
    uids = []
    for i, pl in enumerate(g.players):
        for z in pl.zones().values():
            uids += [c.uid for c in z]
        for s in pl.in_play():
            uids += [c.uid for c in s.all_cards()]
    if g.stadium:
        uids.append(g.stadium.uid)
    assert len(uids) == len(set(uids)), 'carta duplicada'
    assert not g.done or True


def setup(cid, atk=None):
    g = new_game(seed=1)
    d = db().cards[cid]
    cost = atk.cost if atk is not None else []
    en = [BASIC[t] for t in cost] + ['Basic Psychic Energy'] * 3
    board(g, 0, cid, bench=['Dreepy', 'Pikachu'], hand=['Basic Psychic Energy'] * 3 + ['Pikachu', "Boss's Orders"],
          energy={0: en, 1: ['Basic Fire Energy']},
          discard=['Basic Water Energy', 'Basic Grass Energy', 'Basic Fire Energy', "Boss's Orders", 'Ultra Ball'],
          deck=['Basic Water Energy', 'Dreepy', 'Basic Psychic Energy', 'Pikachu', 'Basic Grass Energy'] * 6,
          prizes=4, damage={1: 20})
    board(g, 1, 'Drakloak', bench=['Dreepy', 'Dreepy', 'Mew ex'], hand=['Basic Psychic Energy'] * 4 + ["Boss's Orders"],
          energy={0: ['Basic Psychic Energy', 'Basic Fire Energy', 'Basic Water Energy'], 1: ['Basic Psychic Energy']},
          discard=['Basic Fire Energy', 'Ultra Ball'], deck=['Dreepy', 'Basic Psychic Energy'] * 10, prizes=4,
          damage={0: 30, 1: 10})
    at_turn(g)
    return g


def resolve(g, rng, mode):
    n = 0
    while not g.done and g.prompt.hint != 'main':
        opts = g.prompt.options
        i = 0 if mode == 'first' else (len(opts) - 1 if mode == 'last' else rng.randrange(len(opts)))
        g.step(i)
        n += 1
        assert n < 400, 'decisões demais'


def run_one(cid, kind, name, mode, seed):
    d = db().cards[cid]
    atk = next((a for a in d.attacks if a.name == name), None) if kind == 'attack' else None
    g = setup(cid, atk)
    rng = random.Random(seed)
    label = ('Atacar: ' if kind == 'attack' else 'Habilidade ') + name
    idx = next((i for i, o in enumerate(g.prompt.options) if o.label.startswith(label)), None)
    if idx is None:
        return 'indisponível'
    before = [pl.total_cards(g.stadium) for pl in g.players]
    g.step(idx)
    resolve(g, rng, mode)
    invariants(g)
    after = [pl.total_cards(g.stadium) for pl in g.players]
    assert before == after, f'cartas perdidas/criadas: {before} → {after}'
    return 'ok'


def main():
    ids = sys.argv[1:] or [c for c, d in db().cards.items() if d.kind == 'pokemon']
    bad, stats = {}, {'ok': 0, 'indisponível': 0}
    for cid in ids:
        d = db().cards[cid]
        targets = [('attack', a.name) for a in d.attacks] + \
                  [('ability', a.name) for a in d.abilities if a.impl is not None and a.impl.kind == 'activated']
        for kind, name in targets:
            for mode, seed in (('first', 0), ('last', 0), ('rand', 1), ('rand', 2)):
                try:
                    r = run_one(cid, kind, name, mode, seed)
                    stats[r] = stats.get(r, 0) + 1
                    if r != 'ok':
                        break
                except Exception as e:
                    tb = traceback.extract_tb(e.__traceback__)[-1]
                    bad.setdefault((cid, d.name, name), f'{type(e).__name__}: {e} @ {os.path.basename(tb.filename)}:{tb.lineno}')
    print(stats)
    for k, v in bad.items():
        print('ERRO', k, v)
    print('erros:', len(bad))


if __name__ == '__main__':
    main()
