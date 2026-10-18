"""Habilidades escritas à mão — segunda leva (passivas com ganchos/eventos e gatilhos de movimento)."""
from __future__ import annotations

import re

from ..core import AbilityImpl
from ..engine import run
from . import ability, lib
from .abilities import passive
from .compiler import Exec, cond_expr


def once(g, key) -> bool:
    """True na primeira consulta de `key` (efeitos que 'não acumulam')."""
    seen = g.__dict__.setdefault('_once', set())
    if key in seen:
        return False
    seen.add(key)
    return True


def canonical(g, src, name) -> bool:
    """Entre várias cópias da mesma Habilidade do mesmo jogador, só a de menor id vale (não acumula)."""
    ids = [s.sid for s in g.players[src.owner].in_play()
           if any(a.name == name and g.ability_active(s, a) for a in s.d.abilities)]
    return bool(ids) and min(ids) == src.slot.sid


def _opp(src, ctx):
    return ctx.player != src.owner


# ====================================================================== dano em contra-ataque / ao ser atingido
def _on_damaged(cond_slot, action):
    """Evento damaged_by_attack: cond_slot(g, src, slot) decide, action(g, src, ctx, slot, damage) age."""
    def ev(g, src, ctx, slot, damage):
        if ctx.player != src.owner and cond_slot(g, src, slot) and g.in_play(ctx.attacker):
            return action(g, src, ctx, slot, damage)
    return AbilityImpl(kind='passive', events={'damaged_by_attack': ev})


@ability('Counterattack Grouping')
def _(d, ab):
    return _on_damaged(lambda g, src, s: s.owner == src.owner and g.is_active(s) and s.name in ('Wishiwashi', 'Wishiwashi ex'),
                       lambda g, src, ctx, s, dmg: g.place_counters(ctx.attacker, 3, 'ability', by=src.owner))


@ability('Spiteful Swirl')
def _(d, ab):
    return _on_damaged(lambda g, src, s: s.owner == src.owner and g.is_active(s) and g.has_type(s, 'D'),
                       lambda g, src, ctx, s, dmg: g.place_counters(ctx.attacker, 1, 'ability', by=src.owner))


@ability('Shell Spikes')
def _(d, ab):
    def act(g, src, ctx, s, dmg):
        a = ctx.attacker
        if a.energy:
            yield from lib.discard_energy_from(g, src.owner, a, 1, None, None, src.slot.top)
    return _on_damaged(lambda g, src, s: s is src.slot and g.is_active(s), act)


@ability('Smog Signals')
def _(d, ab):
    def act(g, src, ctx, s, dmg):
        yield from lib.search_to_bench(g, src.owner, lambda c: c.d.kind == 'pokemon' and c.d.is_basic and
                                       'Koffing' in c.d.name, 2, src.slot.top)
    return _on_damaged(lambda g, src, s: s is src.slot and g.is_active(s), act)


# ====================================================================== nocautes
@ability('Fainting Spell')
def _(d, ab):
    def ev(g, src, slot, owner, by_attack, attacker, dest):
        if slot is src.slot and by_attack and attacker is not None and g.in_play(attacker) and g.flip():
            attacker.damage = max(attacker.damage, g.hp(attacker))
            g.say(f'{attacker.name} foi Nocauteado por {src.slot.name}')
    return AbilityImpl(kind='passive', events={'knocked_out': ev})


@ability('Infinite Shadow')
def _(d, ab):
    def ev(g, src, slot, owner, by_attack, attacker, dest):
        if slot is src.slot and by_attack:
            dest['to'] = 'hand'
    return AbilityImpl(kind='passive', events={'knocked_out': ev})


@ability("Diver's Catch")
def _(d, ab):
    def ev(g, src, slot, owner, by_attack, attacker, dest):
        if owner == src.owner and by_attack and g.has_type(slot, 'W'):
            es = [e for e in slot.energy if e.d.basic_energy and e.d.provides == 'W']
            if es:
                if (yield from g.yes_no(owner, 'Devolver as Energias Água Básicas à mão?', source=src.slot.top)):
                    for e in es:
                        dest['redirect'][e.uid] = 'hand'
    return AbilityImpl(kind='passive', events={'knocked_out': ev})


@ability('Photon Cord')
def _(d, ab):
    def ev(g, src, slot, owner, by_attack, attacker, dest):
        if slot is not src.slot or not by_attack or g.players[owner].active is not slot:
            return
        pool = [e for e in slot.energy if e.d.basic_energy and e.d.provides == 'L']
        bench = g.players[owner].bench
        if not pool or not bench:
            return
        got = yield from g.choose_cards(owner, pool, 2, 1, 'pick', 'Energias Raio para o Banco', slot.top,
                                        key=lambda c: c.uid)
        if not got:
            return
        t = yield from g.choose_slot(owner, bench, 'attach_target', 'Mover para qual Pokémon do Banco?', slot.top)
        for e in got:
            slot.energy.remove(e)
            t.energy.append(e)
    return AbilityImpl(kind='passive', events={'knocked_out': ev})


@ability('Wonder Kiss')
def _(d, ab):
    def ev(g, src, slot, owner, by_attack, attacker, dest):
        if owner != src.owner and g.players[owner].active is slot and once(g, ('wonder', g.turn, slot.sid)):
            if g.flip():
                g.take_prizes(src.owner, 1)
    return AbilityImpl(kind='passive', events={'knocked_out': ev})


def _prize_hook(pred, delta=None, zero=False):
    def h(g, src, v, slot, taker, by_attack, attacker):
        if pred(g, src, slot, by_attack, attacker, taker):
            return 0 if zero else max(0, v + delta)
    return AbilityImpl(kind='passive', hooks={'prizes': h})


@ability('Fragile Husk')
def _(d, ab):
    return _prize_hook(lambda g, src, s, by, att, taker: s is src.slot and by and att is not None and att.d.is_ex, zero=True)


@ability("Oh No You Don't")
def _(d, ab):
    return _prize_hook(lambda g, src, s, by, att, taker: s is src.slot and by and
                       any(x.name == 'Pecharunt ex' for x in g.players[src.owner].in_play()), -1)


@ability('Shadowy Concealment')
def _(d, ab):
    return _prize_hook(lambda g, src, s, by, att, taker: s.owner == src.owner and by and g.has_type(s, 'D') and
                       att is not None and att.d.is_ex and canonical(g, src, 'Shadowy Concealment'), -1)


@ability('Greedy Eater')
def _(d, ab):
    return _prize_hook(lambda g, src, s, by, att, taker: by and att is src.slot and s.d.stage == 0, +1)


# ====================================================================== eventos de ligar Energia / evoluir
@ability('Auto Heal')
def _(d, ab):
    def ev(g, src, player, card, slot, from_hand):
        if from_hand and player == src.owner and g.is_active(src.slot) and slot.owner == src.owner:
            g.heal(slot, 90)
    return AbilityImpl(kind='passive', events={'energy_attached': ev})


@ability('Gnawing Curse')
def _(d, ab):
    def ev(g, src, player, card, slot, from_hand):
        if from_hand and player != src.owner:
            g.place_counters(slot, 2, 'ability', by=src.owner)
    return AbilityImpl(kind='passive', events={'energy_attached': ev})


@ability('Darkest Impulse')
def _(d, ab):
    def ev(g, src, player, slot, from_hand):
        if from_hand and player != src.owner and once(g, ('darkest', g.turn, slot.sid, len(slot.cards))):
            g.place_counters(slot, 4, 'ability', by=src.owner)
    return AbilityImpl(kind='passive', events={'evolved': ev})


# ====================================================================== Checkup
@ability('Magma Surge')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'checkup_counters': lambda g, src, v, slot, cond:
                                              v + 3 if cond == 'burned' and slot.owner != src.owner else None})


@ability('Toxic Subjugation')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'checkup_counters': lambda g, src, v, slot, cond:
                                              v + 5 if cond == 'poisoned' and slot.owner != src.owner and
                                              g.is_active(src.slot) else None})


@ability('Sand Stream')
def _(d, ab):
    def ev(g, src):
        if not g.is_active(src.slot):
            return
        for s in list(g.players[1 - src.owner].in_play()):
            if s.d.stage == 0:
                g.place_counters(s, 2, 'ability', by=src.owner)
    return AbilityImpl(kind='passive', events={'checkup': ev})


@ability('Good Sleep')
def _(d, ab):
    def ev(g, src):
        s = src.slot
        if 'asleep' in s.conditions and s.flags.get('stayed_asleep') == g.turn:
            g.heal(s, 9999)
    return AbilityImpl(kind='passive', events={'checkup': ev})


# ====================================================================== quando o Ativo vai para o Banco
def _bench_trigger(action):
    def ev(g, src, player, slot, cause):
        if player != src.owner and g.is_active(src.slot) and g.current == player:
            new = g.players[player].active
            if new is not None:
                return action(g, src, slot, new)
    return ev


@ability('Holes')
def _(d, ab):
    def ev(g, src, player, slot, cause):
        if player != src.owner and g.current == player:
            g.place_counters(slot, 2, 'ability', by=src.owner)
    return AbilityImpl(kind='passive', events={'moved_to_bench': ev})


@ability('Swirling Prose')
def _(d, ab):
    return AbilityImpl(kind='passive', events={'moved_to_bench': _bench_trigger(
        lambda g, src, old, new: g.add_condition(new, 'confused'))})


@ability('Lava Zone')
def _(d, ab):
    return AbilityImpl(kind='passive', events={'moved_to_bench': _bench_trigger(
        lambda g, src, old, new: g.add_condition(new, 'burned'))})


# ====================================================================== bloqueio de Habilidades
@ability('Damp')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'ability_blocked': lambda g, src, slot, ability:
                                              True if ability.impl is not None and ability.impl.self_ko else None})


@ability('Sticky Bind')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'ability_blocked': lambda g, src, slot, ability:
                                              True if not g.is_active(src.slot) and not g.is_active(slot) and
                                              slot.d.stage == 2 else None})


@ability('Initialization')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'ability_blocked': lambda g, src, slot, ability:
                                              True if g.is_active(src.slot) and slot.d.rule_box and
                                              'future' not in slot.d.tags and ability.name != 'Luminous Wing' else None})


@ability('Midnight Fluttering')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'ability_blocked': lambda g, src, slot, ability:
                                              True if g.is_active(src.slot) and slot.owner != src.owner and
                                              g.is_active(slot) and ability.name != 'Midnight Fluttering' else None})


@ability('Potent Glare')
def _(d, ab):
    def h(g, src, player, card):
        if player != src.owner and g.is_active(src.slot) and card.d.kind == 'pokemon' and card.d.abilities and \
                card.d.family != "Team Rocket's":
            return False
    return AbilityImpl(kind='passive', hooks={'can_play': h})


@ability('Luminous Wing')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'prevent_counters': lambda g, src, target, kind, by:
                                              target is src.slot and kind == 'ability' and by != src.owner})


@ability('Mentally Calm')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'no_return_to_hand': lambda g, src, slot: slot.owner != src.owner})


@ability('Life-Locked')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'can_heal': lambda g, src, slot:
                                              False if slot.owner != src.owner and g.is_active(slot) else None})


# ====================================================================== efeitos de Treinadores bloqueados
def _trainer_shield(kinds, whose):
    def h(g, src, card, target):
        if card.owner == src.owner or card.d.subtype not in kinds:
            return None
        return whose(g, src, target)
    return AbilityImpl(kind='passive', hooks={'prevent_trainer_effects': h})


@ability('Snow Camouflage')
def _(d, ab):
    return _trainer_shield(('item', 'supporter'), lambda g, src, t: t is src.slot)


@ability('Unnerve')
def _(d, ab):
    return _trainer_shield(('item', 'supporter'), lambda g, src, t: t is src.slot)


@ability('Wide Wall')
def _(d, ab):
    return _trainer_shield(('supporter',), lambda g, src, t: g.is_active(src.slot) and t.owner == src.owner)


# ====================================================================== dano / defesa
def _less_damage_team(pred_target, n, cond_src=None):
    def h(g, src, dmg, ctx, target, active):
        if target.owner != src.owner or not _opp(src, ctx) or not pred_target(g, src, target):
            return None
        if cond_src is not None and not cond_src(g, src):
            return None
        key = ('nostack', src.effect.name if src.effect else ab_name(src), id(ctx), target.sid)
        if ctx.data.get(key):
            return None
        ctx.data[key] = True
        return dmg - n
    return h


def ab_name(src):
    return src.card.name if src.card is not None else ''


@ability('Stone Palace')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'damage_in': _less_damage_team(
        lambda g, src, t: t.d.family == "Steven's", 30, lambda g, src: not g.is_active(src.slot))})


@ability('Tundra Wall')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'damage_in': _less_damage_team(
        lambda g, src, t: g.has_energy_type(t, 'W'), 50)})


@ability('Curly Wall')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'damage_in': _less_damage_team(
        lambda g, src, t: t.d.stage == 0 and g.has_type(t, 'C'), 60,
        lambda g, src: any(s is not src.slot and s.name == 'Bouffalant' for s in g.players[src.owner].in_play()))})


@ability('Extra Helpings')
def _(d, ab):
    def h(g, src, dmg, ctx, target):
        a = ctx.attacker
        if a.owner != src.owner or a.d.family != "Hop's":
            return None
        key = ('nostack', 'Extra Helpings', id(ctx))
        if ctx.data.get(key):
            return None
        ctx.data[key] = True
        return dmg + 30
    return AbilityImpl(kind='passive', hooks={'damage_out': h})


@ability('Gloomy Garbage')
def _(d, ab):
    f = lambda g, src, dmg, ctx, target: (dmg - 20 if ctx.player != src.owner and ctx.attacker.tools
                                          and g.is_active(ctx.attacker) else None)
    # ruling 2345: também reduz o dano que o ataque faz aos Pokémon do Banco (gancho próprio, sem Fraqueza/Resistência)
    return AbilityImpl(kind='passive', hooks={'damage_out': f, 'damage_out_bench': f})


@ability('Vibrant Dance')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'hp': lambda g, src, v, slot:
                                              v + 40 if slot.owner == src.owner and canonical(g, src, 'Vibrant Dance')
                                              else None})


@ability('Azure Seas')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'ignore_effects': lambda g, src, ctx: ctx.attacker is src.slot})


@passive(r"If (.+?), attacks used by this Pokémon do (\d+) more damage to your opponent's Active Pokémon")
def _(m, d, ab):
    cond = cond_expr(m.group(1))
    n = int(m.group(2))

    def h(g, src, dmg, ctx, target):
        if ctx.attacker is src.slot and cond(Exec(g, src.owner, slot=src.slot)):
            return dmg + n
    return AbilityImpl(kind='passive', hooks={'damage_out': h})


@ability('Adrena-Power')
def _(d, ab):
    def ok(g, s):
        return g.has_energy_type(s, 'D')
    return AbilityImpl(kind='passive', hooks={
        'hp': lambda g, src, v, slot: v + 100 if slot is src.slot and ok(g, slot) else None,
        'damage_out': lambda g, src, dmg, ctx, target: dmg + 100 if ctx.attacker is src.slot and ok(g, src.slot) else None})


@ability('Resilient Soul')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'hp': lambda g, src, v, slot:
                                              v + 50 * g.prizes_taken(1 - src.owner) if slot is src.slot else None})


@ability('Craftsmanship')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'hp': lambda g, src, v, slot:
                                              v + 40 * g.energy_count(slot, 'F') if slot is src.slot else None})


@ability('Dual Core')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'types': lambda g, src, v, slot:
                                              ['F', 'M'] if slot is src.slot and
                                              any(t.name == 'Future Booster Energy Capsule' for t in slot.tools) else None})


@ability('Supereffective Pheromones')
def _(d, ab):
    def h(g, src, v, slot):
        if g.is_active(slot) and any(s.name == 'Volbeat' for s in g.players[src.owner].in_play()):
            return (v[0], 3)
    return AbilityImpl(kind='passive', hooks={'weakness': h})


@ability('Multi Adapter')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'tool_slots': lambda g, src, v, slot:
                                              2 if slot.owner == src.owner and 'Rotom' in slot.name else None})


# ====================================================================== ataques extras / custo
@ability('Memory Helix')
def _(d, ab):
    def h(g, src, atks, slot):
        if slot is src.slot:
            return atks + [a for s in g.players[src.owner].bench for a in s.d.attacks if a not in atks]
    return AbilityImpl(kind='passive', hooks={'extra_attacks': h})


@ability('Memory Dive')
def _(d, ab):
    def h(g, src, atks, slot):
        if slot.owner != src.owner or not slot.evolved:
            return None
        extra = [a for c in slot.cards[:-1] if c.d.kind == 'pokemon' for a in c.d.attacks
                 if a not in slot.d.attacks and a not in atks]
        return atks + extra if extra else None
    return AbilityImpl(kind='passive', hooks={'extra_attacks': h})


def _cost_less(count_fn, only_attack=None):
    def h(g, src, cost, slot, attack):
        if slot is not src.slot or (only_attack and attack.name != only_attack):
            return None
        c = list(cost)
        for _ in range(count_fn(g, src)):
            if 'C' in c:
                c.remove('C')
        return c
    return AbilityImpl(kind='passive', hooks={'attack_cost': h})


@ability('Hustle Play')
def _(d, ab):
    return _cost_less(lambda g, src: len(g.players[1 - src.owner].bench))


@ability('Seasoned Skill')
def _(d, ab):
    return _cost_less(lambda g, src: g.prizes_taken(1 - src.owner), 'Blood Moon')


@ability('Food Prep')
def _(d, ab):
    return _cost_less(lambda g, src: sum(1 for c in g.players[src.owner].discard if c.name == 'Kofu'))


def _cost_set(cond, new_cost=None, attack_name=None, only_colorless=False):
    def h(g, src, cost, slot, attack):
        if slot is not src.slot or (attack_name and attack.name != attack_name) or not cond(g, src):
            return None
        if only_colorless:
            return [t for t in cost if t != 'C']
        return list(new_cost)
    return AbilityImpl(kind='passive', hooks={'attack_cost': h})


@ability('Tuning Echo')
def _(d, ab):
    return _cost_set(lambda g, src: len(g.players[0].hand) == len(g.players[1].hand), [], 'Frightening Howl')


@ability("Sniper's Eye")
def _(d, ab):
    return _cost_set(lambda g, src: len(g.players[1 - src.owner].hand) == 4, only_colorless=True)


@ability('Plasma Bane')
def _(d, ab):
    return _cost_set(lambda g, src: any('Colress' in c.name for c in g.players[1 - src.owner].discard), ['C'], 'Trifrost')


@ability('Glistening Bubbles')
def _(d, ab):
    return _cost_set(lambda g, src: any('tera' in s.d.tags for s in g.players[src.owner].in_play()), ['P'], 'Double-Edge')


@ability('Born to Slack')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'can_attack': lambda g, src, slot, attack:
                                              False if slot is src.slot and not any(
                                                  s.d.is_ex or 'v' in s.d.tags for s in g.players[1 - src.owner].in_play())
                                              else None})


@ability('Power Saver')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'can_attack': lambda g, src, slot, attack:
                                              False if slot is src.slot and sum(
                                                  1 for s in g.players[src.owner].in_play()
                                                  if s.d.family == "Team Rocket's") < 4 else None})


@ability('Debut Performance')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'first_turn_attack': lambda g, src, slot:
                                              slot is src.slot and g.players[src.owner].went_first})


# ====================================================================== evolução antecipada
def _evolve_early(cond):
    def h(g, src, slot, card):
        if slot is src.slot and cond(g, src):
            return True
    return AbilityImpl(kind='passive', hooks={'can_evolve_early': h})


@ability('Stimulated Evolution')
def _(d, ab):
    other = 'Shelmet' if d.name == 'Karrablast' else 'Karrablast'
    return _evolve_early(lambda g, src: any(s.name == other for s in g.players[src.owner].in_play()))


@ability('Fighting Roar')
def _(d, ab):
    return _evolve_early(lambda g, src: g.players[1 - src.owner].active is not None and
                         g.players[1 - src.owner].active.d.is_ex)


@ability('Boosted Evolution')
def _(d, ab):
    return _evolve_early(lambda g, src: g.is_active(src.slot))


@ability('Rainbow DNA')
def _(d, ab):
    def h(g, src, frm, slot, card):
        if slot is src.slot and card.d.is_ex and card.d.evolves_from == 'Eevee':
            return set(frm) | {slot.name}
    return AbilityImpl(kind='passive', hooks={'evolves_from': h})


@ability("Hero's Spirit")
def _(d, ab):
    return AbilityImpl(kind='passive', hand_blocked=True)


# ====================================================================== gatilhos de movimento (Banco ↔ Ativo)
def trigger(g, src, slot, run_fn, ask_text, name):
    if not (yield from g.yes_no(src.owner, ask_text, source=src.slot.top)):
        return
    src.slot.ability_turns[name] = g.turn
    g.say(f'{g.players[src.owner].name} usou {name}', 'ability')
    yield from run(run_fn(g, src.owner, src.slot, slot))


def _trigger_ability(name, event, who_slot, run_fn, ask_text):
    def ev(g, src, player, slot, cause):
        if player != src.owner or g.current != player or not who_slot(g, src, slot):
            return
        if src.slot.ability_turns.get(name) == g.turn:
            return
        return trigger(g, src, slot, run_fn, ask_text, name)
    return AbilityImpl(kind='passive', events={event: ev})


@ability('Metal Road')
def _(d, ab):
    def run_(g, p, s, moved):
        yield from lib.move_energy(g, p, lambda: [x for x in g.players[p].in_play() if x is not s], lambda: [s], 99,
                                   lambda e: e.d.provides == 'M' and e.d.basic_energy, s.top)
    return _trigger_ability('Metal Road', 'moved_to_active', lambda g, src, sl: sl is src.slot, run_,
                            'Usar Metal Road?')


@ability('Lustrous Assist')
def _(d, ab):
    def run_(g, p, s, moved):
        yield from lib.move_energy(g, p, lambda: list(g.players[p].bench), lambda: [moved], 99, None, s.top)
    return _trigger_ability('Lustrous Assist', 'moved_to_active', lambda g, src, sl: sl.name == 'Mega Latias ex' and
                            sl.owner == src.owner, run_, 'Usar Lustrous Assist?')


@ability('Buzzing Boost')
def _(d, ab):
    def run_(g, p, s, moved):
        yield from lib.search_attach(g, p, lambda c: c.d.basic_energy and c.d.provides == 'G', 3, lambda: [s], s.top)
    return _trigger_ability('Buzzing Boost', 'moved_to_active', lambda g, src, sl: sl is src.slot, run_,
                            'Usar Buzzing Boost?')


@ability('Fall Back to Reload')
def _(d, ab):
    def run_(g, p, s, moved):
        pl = g.players[p]
        got = yield from g.choose_cards(p, [c for c in pl.hand if c.d.basic_energy and c.d.provides == 'W'], 2, 0,
                                        'attach_from_hand', 'Energias Água da mão', s.top)
        for c in got:
            pl.hand.remove(c)
        yield from lib.attach_cards(g, p, got, lambda: [s], s.top)
    return _trigger_ability('Fall Back to Reload', 'moved_to_bench', lambda g, src, sl: sl is src.slot, run_,
                            'Usar Fall Back to Reload?')


@ability('Zero to Hero')
def _(d, ab):
    def run_(g, p, s, moved):
        pl = g.players[p]
        cands = [c for c in pl.deck if c.name == 'Palafin ex']
        got = yield from g.choose_cards(p, cands, 1, 0, 'search', 'Palafin ex', s.top)
        if got:
            new = got[0]
            pl.deck.remove(new)
            old = s.cards[0]
            s.cards[0] = new
            pl.deck.append(old)
            g.shuffle(p)
        else:
            g.shuffle(p)
    return _trigger_ability('Zero to Hero', 'moved_to_bench', lambda g, src, sl: sl is src.slot, run_,
                            'Usar Zero to Hero?')


# ====================================================================== ativadas escritas à mão
@ability('Fan Call')
def _(d, ab):
    def run_(g, p, s):
        yield from lib.search_to_hand(g, p, lambda c: c.d.kind == 'pokemon' and 'C' in c.d.types and
                                      c.d.hp <= 100, 3, s.top)
    return AbilityImpl(can_use=lambda g, p, s: g.first_turn(p) and bool(g.players[p].deck), run=run_,
                       shared_key='Fan Call')


@ability('Emergency Rotation')
def _(d, ab):
    def can(g, p, c):
        return g.bench_space(p) > 0 and any(s.d.stage == 2 for s in g.players[1 - p].in_play())

    def run_(g, p, c):
        pl = g.players[p]
        if c in pl.hand:
            pl.hand.remove(c)
            yield from g.play_to_bench(p, c, from_hand=False)
    return AbilityImpl(kind='hand', can_use=can, run=run_)


@ability('Explosiveness')
def _(d, ab):
    return AbilityImpl(kind='setup')


@ability('Sandy Flapping')
def _(d, ab):
    def run_(g, p, s):
        lib.mill(g, 1 - p, 2)
        if False:
            yield

    def ev(g, src, slot, owner, by_attack, attacker, dest):
        if slot is src.slot and by_attack and g.players[owner].active is slot:
            if (yield from g.yes_no(owner, 'Usar Sandy Flapping?', source=slot.top)):
                lib.mill(g, 1 - owner, 2)
    return AbilityImpl(kind='on_evolve', run=run_, events={'knocked_out': ev})


@ability('Captivating Invitation')
def _(d, ab):
    def run_(g, p, s):
        if not g.flip():
            return
        t = yield from lib.gust(g, p, source=s.top)
        if t is not None:
            g.add_condition(t, 'confused')
    return AbilityImpl(can_use=lambda g, p, s: bool(g.players[1 - p].bench), run=run_)


@ability('Slimy Sliding')
def _(d, ab):
    def h(g, src, player, slot):
        if player != src.owner and canonical(g, src, 'Slimy Sliding'):
            return not g.flip()
    return AbilityImpl(kind='passive', hooks={'retreat_fizzle': h})


@ability('Startling Drop')
def _(d, ab):
    return AbilityImpl(kind='passive')   # a lógica está em lib.mill (a carta age de dentro do baralho)
