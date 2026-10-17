"""Auxiliares para montar posições exatas em testes de cenário."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ptcg.carddb import db  # noqa: E402
from ptcg.core import Card, PokemonSlot  # noqa: E402
from ptcg.engine import Game  # noqa: E402

_UID = [10000]


def card(name, owner):
    _UID[0] += 1
    d = db().get(name) if name in db().cards else db().resolve(name)
    return Card(_UID[0], d, owner)


FILLER = ['Basic Psychic Energy'] * 50 + ['Pikachu'] * 10


def new_game(seed=0):
    """Partida com decks neutros; jogador 0 começa; para no turno 1 (fase principal)."""
    D = db()
    deck = ['Dreepy'] * 20 + ['Basic Psychic Energy'] * 40
    g = Game([D.resolve(x).id for x in deck], [D.resolve(x).id for x in deck], seed=seed, first_player=0)
    while g.prompt.hint != 'main':
        g.step(len(g.prompt.options) - 1 if g.prompt.hint == 'setup_bench' else 0)
    return g


def board(g, p, active=None, bench=(), hand=(), energy=None, discard=(), deck=None, tools=None, prizes=None,
          damage=None):
    """Substitui completamente a posição do jogador p. energy/tools/damage: {pos: [...]} (0 = ativo)."""
    pl = g.players[p]
    pl.bench = []
    pl.active = PokemonSlot(card(active, p), 0) if active else None
    for b in bench:
        pl.bench.append(PokemonSlot(card(b, p), 0))
    slots = pl.in_play()
    for pos, es in (energy or {}).items():
        slots[pos].energy = [card(e, p) for e in es]
    for pos, ts in (tools or {}).items():
        slots[pos].tools = [card(t, p) for t in ts]
    for pos, dmg in (damage or {}).items():
        slots[pos].damage = dmg
    pl.hand = [card(h, p) for h in hand]
    pl.discard = [card(x, p) for x in discard]
    if deck is not None:
        pl.deck = [card(x, p) for x in deck]
    if prizes is not None:
        pl.prizes = [card('Basic Psychic Energy', p) for _ in range(prizes)]


def at_turn(g, turn=5):
    g.turn = turn
    for pl in g.players:
        pl.turns_taken = 3
    g.refresh()


def labels(g):
    return [o.label for o in g.prompt.options]


def act(g, text, exact=False):
    for i, o in enumerate(g.prompt.options):
        if (o.label == text) if exact else (text in o.label):
            g.step(i)
            return
    raise AssertionError(f'opção {text!r} não encontrada em {labels(g)} ({g.prompt.text})')


def has(g, text):
    return any(text in o.label for o in g.prompt.options)


def resolve_all(g, choose='first'):
    """Responde prompts que não sejam a fase principal escolhendo a primeira opção."""
    while not g.done and g.prompt.hint != 'main':
        g.step(0)
