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
            placed = g.place_counters(t, n, 'attack', by=ctx.player, ctx=ctx)
            if not placed:   # ruling 1979: sem contadores colocados, não embaralha as Energias
                return
        for c in cards:
            pl.discard.remove(c)
            pl.deck.append(c)
        g.shuffle(ctx.player)
    return AttackImpl(run=run_)


@attack('Grimmsnarl', "Goad 'n' Grab")
def _(d, atk):
    def run_(g, ctx):
        # ruling 2025: troca primeiro; só se ocorrer há "novo Ativo" para receber os 160 (Mist Energy impede a troca)
        old = g.players[ctx.opp].active
        if old is None or g.effects_prevented(ctx, old):
            return
        s = yield from lib.opp_switches_out(g, ctx.player, ctx.attacker.top)
        if s is not None:
            ctx.defender = s
            g.deal_attack_damage(ctx, s, 160)
    return AttackImpl(run=run_)


@attack('Alcremie', 'Colorful Confection')
def _(d, atk):
    def run_(g, ctx):
        # rulings 2019/2020: tipos das Energias Básicas ligadas (Luminous Energy não conta); pode repetir tipos
        pl = g.players[ctx.player]
        types = {e.d.provides for e in ctx.attacker.energy if e.d.basic_energy}
        cands = [c for c in pl.deck if c.d.kind == 'pokemon' and types & set(c.d.types)]
        got = yield from g.choose_cards(ctx.player, cands, 5, 0, 'search', 'Colorful Confection: Pokémon', ctx.attacker.top)
        for c in got:
            pl.deck.remove(c)
            pl.hand.append(c)
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
