"""Estádios."""
from __future__ import annotations

from ..core import DEFAULT_BENCH, TrainerImpl
from . import lib, register_trainer


def stadium(name, **kw):
    return register_trainer(name, TrainerImpl(**kw))


def basic(t=None):
    return lambda c: c.d.basic_energy and (t is None or c.d.provides == t)


def _academy(g, p):
    pl = g.players[p]
    c = yield from g.choose_cards(p, pl.hand, 1, 1, 'pick', 'Carta para o topo do baralho', g.stadium)
    pl.hand.remove(c[0])
    pl.deck.insert(0, c[0])


stadium('Academy at Night', action=_academy, action_can=lambda g, p: bool(g.players[p].hand))
stadium('Ange Floette', hooks={'hp': lambda g, src, v, slot: v + 150 if slot.name == 'Mega Floette ex' else None},
        can_play=lambda g, p, c: g.stadium is not None and g.stadium.name == 'Prism Tower')


def _az_bench(g, src, v, player):
    if any('tera' in s.d.tags for s in g.players[player].in_play()):
        return 8


def _az_trim(g, p, limit=5):
    pl = g.players[p]
    while len(pl.bench) > limit:
        s = yield from g.choose_slot(p, pl.bench, 'discard_bench', 'Descartar Pokémon do Banco', g.stadium)
        g.remove_slot(s, 'discard')


def _az_leave(g, src):
    yield from _az_trim(g, src.owner)
    yield from _az_trim(g, 1 - src.owner)


def _az_check(g, src, player):
    for q in (0, 1):
        if len(g.players[q].bench) > g.bench_max(q):
            yield from _az_trim(g, q, g.bench_max(q))


stadium('Area Zero Underdepths', hooks={'bench_max': _az_bench}, events={'leave': _az_leave, 'turn_end': _az_check})
stadium('Battle Cage', hooks={'prevent_counters': lambda g, src, target, kind, by:
                              kind in ('attack', 'ability') and not g.is_active(target) and by is not None
                              and by != target.owner})


def _fanfare(g, p):
    for s in g.players[p].in_play():
        g.heal(s, 10)
    g.turn_ended = True


stadium('Celebratory Fanfare', action=_fanfare)
stadium('Community Center', action=lambda g, p: [g.heal(s, 10) for s in g.players[p].in_play()],
        action_can=lambda g, p: g.players[p].supporter_played)
stadium('Dizzying Valley', status='partial', note='Confusão persiste ao evoluir: não implementado')
stadium('Festival Grounds', hooks={'condition_immune': lambda g, src, slot, cond: bool(slot.energy)})
stadium('Forest of Vitality', hooks={'can_evolve_early': lambda g, src, slot, card:
                                     g.has_type(slot, 'G') and 'G' in card.d.types and not g.first_turn(slot.owner)})


def _quarry(g, p):
    yield from lib.search_to_bench(g, p, lambda c: c.d.as_pokemon and 'Antique' in c.d.name, 2, g.stadium)


stadium('Fossil Quarry', action=_quarry, action_can=lambda g, p: g.bench_space(p) > 0)
stadium('Full Metal Lab', hooks={'damage_in': lambda g, src, dmg, ctx, target, active:
                                 dmg - 30 if g.has_type(target, 'M') and ctx.player != target.owner else None})


def _grand_tree(g, p):
    pl = g.players[p]
    cands = [s for s in pl.in_play() if s.d.stage == 0 and not g.first_turn(p) and s.turn_entered < g.turn
             and any(c.d.stage == 1 and c.d.evolves_from == s.name for c in pl.deck)]
    if not cands:
        g.shuffle(p)
        return
    s = yield from g.choose_slot(p, cands, 'evolve_target', 'Grand Tree: evoluir qual Pokémon?', g.stadium)
    c1 = yield from g.choose_cards(p, [c for c in pl.deck if c.d.stage == 1 and c.d.evolves_from == s.name], 1, 1,
                                   'search', 'Estágio 1', g.stadium)
    pl.deck.remove(c1[0])
    yield from g.evolve(p, s, c1[0], from_hand=False)
    c2 = yield from g.choose_cards(p, [c for c in pl.deck if c.d.stage == 2 and c.d.evolves_from == s.name], 1, 0,
                                   'search', 'Estágio 2 (opcional)', g.stadium)
    if c2:
        pl.deck.remove(c2[0])
        yield from g.evolve(p, s, c2[0], from_hand=False)
    g.shuffle(p)


stadium('Grand Tree', action=_grand_tree)
stadium('Granite Cave', hooks={'damage_in': lambda g, src, dmg, ctx, target, active:
                               dmg - 30 if target.d.family == "Steven's" and ctx.player != target.owner else None})
stadium('Gravity Mountain', hooks={'hp': lambda g, src, v, slot: v - 30 if slot.d.stage == 2 else None})
stadium('Jamming Tower', hooks={'tools_blocked': lambda g, src: True})
stadium('Levincia', action=lambda g, p: lib.recover(g, p, basic('L'), 2, 'hand', g.stadium),
        action_can=lambda g, p: any(basic('L')(c) for c in g.players[p].discard))
stadium('Lively Stadium', hooks={'hp': lambda g, src, v, slot: v + 30 if slot.d.stage == 0 else None})


def _lumiose(g, p):
    yield from lib.search_to_bench(g, p, lambda c: c.d.is_basic, 1, g.stadium)
    g.turn_ended = True


stadium('Lumiose City', action=_lumiose, action_can=lambda g, p: g.bench_space(p) > 0)


def _garden(g, p):
    yield from g.discard_from_hand(p, 1, source=g.stadium, pred=lambda c: c.d.kind == 'energy')
    n = sum(1 for s in g.players[p].in_play() if g.has_type(s, 'P'))
    g.draw_until(p, n)


stadium('Mystery Garden', action=_garden, action_can=lambda g, p: any(c.d.kind == 'energy' for c in g.players[p].hand))
stadium("N's Castle", hooks={'retreat_cost': lambda g, src, v, slot: 0 if slot.d.family == "N's" else None})
stadium('Neutralization Zone', hooks={'damage_in': lambda g, src, dmg, ctx, target, active:
                                      0 if not target.d.rule_box and ctx.attacker.d.rule_box and
                                      ctx.player != target.owner else None})
stadium('Nighttime Mine', hooks={'attack_cost': lambda g, src, cost, slot, attack:
                                 list(cost) + ['C'] if 'tera' in slot.d.tags else None})
stadium('Paradise Resort', hooks={'retreat_cost': lambda g, src, v, slot: v - 1 if slot.name == 'Psyduck' else None})
stadium('Perilous Jungle', hooks={'checkup_counters': lambda g, src, n, slot, cond:
                                  n + 2 if cond == 'poisoned' and not g.has_type(slot, 'D') else None})
stadium('Postwick', hooks={'damage_out': lambda g, src, dmg, ctx, target:
                           dmg + 30 if ctx.attacker.d.family == "Hop's" else None})


def _prism(g, p):
    yield from g.discard_from_hand(p, 2, source=g.stadium)
    g.draw(p, 1)


stadium('Prism Tower', action=_prism, action_can=lambda g, p: len(g.players[p].hand) >= 2)


def _risky(g, src, player, slot, from_hand):
    if player == g.current and slot.d.stage == 0 and not g.has_type(slot, 'D'):
        g.place_counters(slot, 2, 'other')


stadium('Risky Ruins', events={'bench_played': _risky})
stadium('Spikemuth Gym', action=lambda g, p: lib.search_to_hand(g, p, lambda c: c.d.kind == 'pokemon' and
                                                                c.d.family == "Marnie's", 1, g.stadium))


def _surfing(g, p):
    pl = g.players[p]
    s = yield from g.choose_slot(p, [s for s in pl.bench if g.has_type(s, 'W')], 'switch', 'Trocar com', g.stadium)
    if s:
        yield from g.switch_active(p, s)


stadium('Surfing Beach', action=_surfing, action_can=lambda g, p: g.players[p].active is not None and
        g.has_type(g.players[p].active, 'W') and any(g.has_type(s, 'W') for s in g.players[p].bench))
stadium("Team Rocket's Factory", action=lambda g, p: g.draw(p, 2),
        action_can=lambda g, p: any('Team Rocket' in n for n in g.players[p].played
                                    if g.db.named(n) and g.db.named(n)[0].is_supporter))
stadium("Team Rocket's Watchtower", hooks={'ability_blocked': lambda g, src, slot, ability: 'C' in slot.d.types})
