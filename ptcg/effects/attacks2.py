"""Ataques escritos à mão — segunda leva."""
from __future__ import annotations

from ..core import AttackImpl, Option
from ..engine import run
from . import attack, lib


@attack('Kyogre', 'Riptide')
def _(d, atk):
    def pre(g, ctx):
        pl = g.players[ctx.player]
        ctx.data['water'] = [c for c in pl.discard if c.d.basic_energy and c.d.provides == 'W']
        ctx.damage = 20 * len(ctx.data['water'])

    def post(g, ctx):
        pl = g.players[ctx.player]
        for c in ctx.data.get('water', []):
            if c in pl.discard:
                pl.discard.remove(c)
                pl.deck.append(c)
        g.shuffle(ctx.player)

    def est(g, slot, target):
        return 20 * sum(1 for c in g.players[slot.owner].discard if c.d.basic_energy and c.d.provides == 'W')
    return AttackImpl(pre=pre, post=post, estimate=est)


@attack('Sinistcha ex', 'Re-Brew')
def _(d, atk):
    def run_(g, ctx):
        pl = g.players[ctx.player]
        cards = [c for c in pl.discard if c.d.basic_energy and c.d.provides == 'G']
        n = 2 * len(cards)
        if n:
            t = yield from g.choose_slot(ctx.player, g.players[ctx.opp].in_play(), 'counters',
                                         f'Colocar {n} contadores em', ctx.attacker.top)
            g.place_counters(t, n, 'attack', by=ctx.player, ctx=ctx)
        for c in cards:
            pl.discard.remove(c)
            pl.deck.append(c)
        g.shuffle(ctx.player)
    return AttackImpl(run=run_)


@attack('Jynx', 'Inviting Kiss')
def _(d, atk):
    def run_(g, ctx):
        p = ctx.player
        found = yield from lib.search_to_bench(g, p, lambda c: c.d.is_basic, 1, ctx.attacker.top)
        if found:
            new = g.players[p].bench[-1]
            if ctx.attacker.energy:
                yield from lib.move_energy(g, p, lambda: [ctx.attacker], lambda: [new], 1, None, ctx.attacker.top)
    return AttackImpl(run=run_)


@attack('Ditto', 'Surprisingly Transform')
def _(d, atk):
    def run_(g, ctx):
        p = ctx.player
        if not g.flip():
            return
        pl = g.players[p]
        s = ctx.attacker
        got = yield from g.search_deck(p, lambda c: c.d.kind == 'pokemon', 1, 'search', 'Pokémon para trocar',
                                       s.top, shuffle=False)
        if got:
            new = got[0]
            old = s.cards[0]
            s.cards[0] = new
            pl.deck.append(old)
        g.shuffle(p)
    return AttackImpl(run=run_)


@attack('Gholdengo', 'Celebration')
def _(d, atk):
    def can(g, slot):
        return len(g.players[slot.owner].hand) == 30

    def run_(g, ctx):
        p = ctx.player
        if len(g.players[p].hand) == 30:
            g.take_prizes(p, 2)
            g.hand_to_deck(p)
        if False:
            yield
    return AttackImpl(run=run_)
