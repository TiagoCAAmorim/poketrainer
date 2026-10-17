"""Energias especiais."""
from __future__ import annotations

from ..core import ANY, COLORLESS, TrainerImpl
from . import lib, register_trainer


def energy(name, **kw):
    return register_trainer(name, TrainerImpl(**kw))


def T(t):
    return [frozenset({t})]


def on(src, slot):
    return slot is src.slot


energy('Boomerang Energy', units=lambda g, c, s: [COLORLESS])
energy('Bubbly Water Energy', units=lambda g, c, s: T('W'),
       hooks={'condition_immune': lambda g, src, slot, cond: on(src, slot) and g.has_type(slot, 'W')},
       on_attach=lambda g, p, c, s, fh: s.clear_conditions() if g.has_type(s, 'W') else None)
energy('Enriching Energy', units=lambda g, c, s: [COLORLESS],
       on_attach=lambda g, p, c, s, fh: g.draw(p, 4) if fh else None)
energy('Growing Grass Energy', units=lambda g, c, s: T('G'),
       hooks={'hp': lambda g, src, v, slot: v + 20 if on(src, slot) and 'G' in slot.d.types else None})


def _ignition_end(g, src, player):
    if player == src.owner and src.card in src.slot.energy:
        g.discard_energy(src.slot, [src.card])


energy('Ignition Energy', units=lambda g, c, s: [COLORLESS] * (3 if s.d.stage > 0 else 1),
       events={'turn_end': _ignition_end})


def _jet(g, p, c, s, from_hand):
    pl = g.players[p]
    if from_hand and s in pl.bench and pl.active is not None:
        yield from g.switch_active(p, s)


energy('Jet Energy', units=lambda g, c, s: [COLORLESS], on_attach=_jet)


def _legacy_prizes(g, src, n, slot, taker, by_attack, attacker):
    pl = g.players[src.owner]
    if on(src, slot) and by_attack and not pl.legacy_used:
        pl.legacy_used = True
        return n - 1


energy('Legacy Energy', units=lambda g, c, s: [ANY], hooks={'prizes': _legacy_prizes})
energy('Luminous Energy', units=lambda g, c, s: [COLORLESS] if any(e is not c and e.d.special_energy for e in s.energy)
       else [ANY])
energy('Magnetic Metal Energy', units=lambda g, c, s: T('M'),
       hooks={'retreat_cost': lambda g, src, v, slot: 0 if on(src, slot) and g.has_type(slot, 'M') else None})
energy('Mist Energy', units=lambda g, c, s: [COLORLESS],
       hooks={'prevent_attack_effects': lambda g, src, ctx, target: on(src, target) and ctx.player != src.owner})
energy('Neo Upper Energy', units=lambda g, c, s: [ANY, ANY] if s.d.stage == 2 else [COLORLESS])
energy('Nitro Fire Energy', units=lambda g, c, s: T('R'))
energy('Prism Energy', units=lambda g, c, s: [ANY] if s.d.stage == 0 else [COLORLESS])
energy('Rocky Fighting Energy', units=lambda g, c, s: T('F'),
       hooks={'prevent_attack_effects': lambda g, src, ctx, target: on(src, target) and ctx.player != src.owner
              and g.has_type(target, 'F')})
energy('Shadowy Darkness Energy', units=lambda g, c, s: T('D'),
       hooks={'damage_in': lambda g, src, dmg, ctx, target, active:
              0 if on(src, target) and not g.is_active(target) and g.has_type(target, 'D')
              and ctx.player != src.owner else None})


def _spiky(g, src, ctx, slot, damage):
    if slot is src.slot and ctx.player != src.owner and g.is_active(slot) and g.in_play(ctx.attacker):
        g.place_counters(ctx.attacker, 2, 'other', by=src.owner)


energy('Spiky Energy', units=lambda g, c, s: [COLORLESS], events={'damaged_by_attack': _spiky})
energy("Team Rocket's Energy", units=lambda g, c, s: [frozenset({'P', 'D'})] * 2,
       can_attach=lambda g, p, c, s: s.d.family == "Team Rocket's")


def _telepathic(g, p, c, s, from_hand):
    if from_hand and g.has_type(s, 'P') and g.bench_space(p) > 0:
        if (yield from g.yes_no(p, 'Telepathic Psychic Energy: buscar até 2 Básicos Psíquicos?', source=c)):
            yield from lib.search_to_bench(g, p, lambda x: x.d.is_basic and 'P' in x.d.types, 2, c)


energy('Telepathic Psychic Energy', units=lambda g, c, s: T('P'), on_attach=_telepathic)
energy('Voltaic Lightning Energy', units=lambda g, c, s: T('L'),
       hooks={'damage_out': lambda g, src, dmg, ctx, target: dmg + 20 if ctx.attacker is src.slot and
              g.has_type(src.slot, 'L') else None})


# Energias que voltam depois de descartadas pelo próprio ataque
def _boomerang_return(g, card, ctx):
    if g.in_play(ctx.attacker) and card in g.players[card.owner].discard:
        g.players[card.owner].discard.remove(card)
        ctx.attacker.energy.append(card)
        g.say('Boomerang Energy voltou ao Pokémon')


def _nitro_return(g, card, ctx):
    if g.has_type(ctx.attacker, 'R') and card in g.players[card.owner].discard:
        g.players[card.owner].discard.remove(card)
        g.players[card.owner].hand.append(card)
        g.say('Nitro Fire Energy voltou para a mão')


RETURNERS = {'Boomerang Energy': _boomerang_return, 'Nitro Fire Energy': _nitro_return}
