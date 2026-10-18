"""Habilidades: compilação automática por texto + implementações escritas à mão."""
from __future__ import annotations

import re

from ..core import AbilityImpl, NAME_TO_TYPE
from ..engine import run
from . import ability, lib
from .compiler import Exec, Unparsed, compile_text, cond_expr, opp_active_pred, steps_runner
from .lib import TYPE_WORDS, slot_filter

# ===================================================================== passivas (padrões)
PASSIVES = []


def passive(rx):
    def deco(f):
        PASSIVES.append((re.compile('^' + rx + r'\.?$'), f))
        return f
    return deco


def _clean(t):
    t = re.sub(r'\s*\([^)]*\)', '', t or '')
    return re.sub(r'\s+', ' ', t).strip()


def _from_opp(ctx, src):
    return ctx.player != src.owner


def _attacker_filter(desc):
    """'your opponent's Basic Pokémon ex' → f(g, ctx)"""
    d = desc.strip()
    m = re.match(r"^your opponent's (.*)$", d)
    if m:
        d = m.group(1)
    if d in ('Pokémon', ''):
        return lambda g, ctx: True
    if d == 'Pokémon that have an Ability':
        return lambda g, ctx: g.has_ability(ctx.attacker)
    if d == 'Pokémon that have any Special Energy attached':
        return lambda g, ctx: any(e.d.special_energy for e in ctx.attacker.energy)
    m = re.match(r'^Pokémon that have (\d+) or less Energy attached$', d)
    if m:
        n = int(m.group(1))
        return lambda g, ctx: g.energy_count(ctx.attacker) <= n
    types = re.findall(TYPE_WORDS, d)
    if types and re.fullmatch(rf'(?:(?:{TYPE_WORDS})(?:, | or |, or )?)+ Pokémon', d):
        codes = {NAME_TO_TYPE[t] for t in types}
        return lambda g, ctx: bool(set(g.types(ctx.attacker)) & codes)
    f = slot_filter(d)
    return lambda g, ctx: f(g, ctx.attacker)


@passive(r'(?:If this Pokémon has any Energy attached, it|This Pokémon) takes (\d+) less damage from attacks(?: from your opponent\'s (.+?))?(?: after applying Weakness and Resistance)?')
def _(m, d, ab):
    n = int(m.group(1))
    need_energy = m.group(0).startswith('If')
    af = _attacker_filter(m.group(2)) if m.group(2) else (lambda g, ctx: True)

    def h(g, src, dmg, ctx, target, active):
        if target is src.slot and (not need_energy or src.slot.energy) and af(g, ctx):
            return dmg - n
    return AbilityImpl(kind='passive', hooks={'damage_in': h})


@passive(r"All of your (.*?)Pokémon(?: that have any (\w+) Energy attached)? take (\d+) less damage from attacks from your opponent's Pokémon")
def _(m, d, ab):
    f = slot_filter(m.group(1) + 'Pokémon')
    et = NAME_TO_TYPE.get(m.group(2)) if m.group(2) else None
    n = int(m.group(3))
    stack_key = None if 'stack' not in ab.text else ab.name

    def h(g, src, dmg, ctx, target, active):
        if target.owner == src.owner and _from_opp(ctx, src) and f(g, target) and \
                (et is None or g.has_energy_type(target, et)):
            if stack_key:   # "doesn't stack": só a primeira fonte aplica
                key = ('nostack', stack_key, id(ctx), target.sid)
                if ctx.data.get(key):
                    return None
                ctx.data[key] = True
            return dmg - n
    return AbilityImpl(kind='passive', hooks={'damage_in': h})


@passive(r"Prevent all damage (?:from attacks )?done to this Pokémon by attacks from your opponent's (.+?)(?: if that damage is (\d+) or more)?")
def _(m, d, ab):
    af = _attacker_filter(m.group(1))
    cap = int(m.group(2)) if m.group(2) else None

    def h(g, src, dmg, ctx, target, active):
        if target is src.slot and _from_opp(ctx, src) and af(g, ctx) and (cap is None or dmg >= cap):
            return 0
    return AbilityImpl(kind='passive', hooks={'damage_in': h})


@passive(r"Prevent all damage from attacks done to this Pokémon by your opponent's (.+)")
def _(m, d, ab):
    af = _attacker_filter(m.group(1))
    return AbilityImpl(kind='passive', hooks={'damage_in': lambda g, src, dmg, ctx, target, active:
                                              0 if target is src.slot and _from_opp(ctx, src) and af(g, ctx) else None})


@passive(r"Prevent all damage from and effects of attacks (?:from your opponent's (.+?) done to this Pokémon|done to this Pokémon by your opponent's (.+))")
def _(m, d, ab):
    af = _attacker_filter(m.group(1) or m.group(2))
    return AbilityImpl(kind='passive', hooks={
        'damage_in': lambda g, src, dmg, ctx, target, active: 0 if target is src.slot and _from_opp(ctx, src) and af(g, ctx) else None,
        'prevent_attack_effects': lambda g, src, ctx, target: target is src.slot and _from_opp(ctx, src) and af(g, ctx)})


@passive(r"As long as this Pokémon is on your Bench, prevent all damage from and effects of attacks from your opponent's Pokémon done to this Pokémon")
def _(m, d, ab):
    def onbench(g, src, target):
        return target is src.slot and not g.is_active(target)
    return AbilityImpl(kind='passive', hooks={
        'damage_in': lambda g, src, dmg, ctx, target, active: 0 if onbench(g, src, target) and _from_opp(ctx, src) else None,
        'prevent_attack_effects': lambda g, src, ctx, target: onbench(g, src, target) and _from_opp(ctx, src)})


@passive(r"Prevent all damage from and effects of attacks from your opponent's Pokémon done to your Benched Pokémon")
def _(m, d, ab):
    def b(g, src, t):
        return t.owner == src.owner and not g.is_active(t)
    return AbilityImpl(kind='passive', hooks={
        'damage_in': lambda g, src, dmg, ctx, target, active: 0 if b(g, src, target) and _from_opp(ctx, src) else None,
        'prevent_attack_effects': lambda g, src, ctx, target: b(g, src, target) and _from_opp(ctx, src)})


@passive(r"Prevent all damage done to your Benched Pokémon that don't have a Rule Box by attacks from your opponent's Pokémon")
def _(m, d, ab):
    return AbilityImpl(kind='passive', hooks={'damage_in': lambda g, src, dmg, ctx, target, active:
                       0 if target.owner == src.owner and not g.is_active(target) and not target.d.rule_box
                       and _from_opp(ctx, src) else None})


@passive(r"As long as this Pokémon is on your Bench, prevent all damage done to each of your Pokémon by attacks from your opponent's (.+)")
def _(m, d, ab):
    af = _attacker_filter(m.group(1))
    return AbilityImpl(kind='passive', hooks={'damage_in': lambda g, src, dmg, ctx, target, active:
                       0 if not g.is_active(src.slot) and target.owner == src.owner and _from_opp(ctx, src)
                       and af(g, ctx) else None})


@passive(r"Prevent all effects of (?:attacks used by your opponent's Pokémon|your opponent's Pokémon's attacks and Abilities) done to (this Pokémon|your (.+))")
def _(m, d, ab):
    if m.group(1) == 'this Pokémon':
        f = lambda g, src, t: t is src.slot
    else:
        sf = slot_filter(m.group(2))
        f = lambda g, src, t: t.owner == src.owner and sf(g, t)
    hooks = {'prevent_attack_effects': lambda g, src, ctx, target: f(g, src, target) and _from_opp(ctx, src)}
    if 'Abilities' in m.group(0):
        hooks['prevent_counters'] = lambda g, src, target, kind, by: f(g, src, target) and kind in ('attack', 'ability') and by != src.owner
    return AbilityImpl(kind='passive', hooks=hooks)


@passive(r"If this Pokémon (?:is in the Active Spot and )?is damaged by an attack from your opponent's Pokémon, (?:put|place) (\d+) damage counters? on the Attacking Pokémon(?: for each (\w+) Energy attached to this Pokémon)?")
def _(m, d, ab):
    n = int(m.group(1))
    et = NAME_TO_TYPE.get(m.group(2)) if m.group(2) else None
    need_active = 'Active Spot' in m.group(0)

    def ev(g, src, ctx, slot, damage):
        if slot is src.slot and ctx.player != src.owner and (not need_active or g.is_active(slot)):
            k = n * (g.energy_count(slot, et) if et else 1)
            if g.in_play(ctx.attacker):
                g.place_counters(ctx.attacker, k, 'ability', by=src.owner)
    return AbilityImpl(kind='passive', events={'damaged_by_attack': ev})


@passive(rf"If this Pokémon is in the Active Spot and is damaged by an attack from your opponent's Pokémon, the Attacking Pokémon is now (Asleep|Burned|Confused|Paralyzed|Poisoned)")
def _(m, d, ab):
    c = lib.cond_word(m.group(1))

    def ev(g, src, ctx, slot, damage):
        if slot is src.slot and ctx.player != src.owner and g.in_play(ctx.attacker):
            g.add_condition(ctx.attacker, c)
    return AbilityImpl(kind='passive', events={'damaged_by_attack': ev})


@passive(r"If this Pokémon has full HP and would be Knocked Out by damage from an attack, it is not Knocked Out, and its remaining HP becomes 10")
def _(m, d, ab):
    return AbilityImpl(kind='passive', hooks={'survive': lambda g, src, slot, damage, ctx:
                                              slot is src.slot and slot.damage == 0})


@passive(r"If this Pokémon would be Knocked Out by damage from an attack, flip a coin. If heads, this Pokémon is not Knocked Out, and its remaining HP becomes 10")
def _(m, d, ab):
    return AbilityImpl(kind='passive', hooks={'survive': lambda g, src, slot, damage, ctx:
                                              slot is src.slot and g.flip()})


@passive(r"(?:If any damage is done to this Pokémon by attacks|If this Pokémon has any Darkness Energy attached and is damaged by an attack), flip a coin. If heads, prevent that damage")
def _(m, d, ab):
    need_d = 'Darkness' in m.group(0)

    def h(g, src, dmg, ctx, target, active):
        if target is src.slot and dmg > 0 and (not need_d or g.has_energy_type(target, 'D')):
            if g.flip():
                return 0
    return AbilityImpl(kind='passive', hooks={'damage_in': h})


@passive(r"This Pokémon can't be (Asleep|Confused|Paralyzed|Poisoned|Burned)")
def _(m, d, ab):
    c = lib.cond_word(m.group(1))
    return AbilityImpl(kind='passive', hooks={'condition_immune': lambda g, src, slot, cond:
                                              slot is src.slot and cond == c})


@passive(r"If this Pokémon has no Energy attached, it has no Retreat Cost")
def _(m, d, ab):
    return AbilityImpl(kind='passive', hooks={'retreat_cost': lambda g, src, v, slot:
                                              0 if slot is src.slot and not slot.energy else None})


@passive(r"(?:Your|All of your) (.*?)Pokémon(?: in play)?(?: that have (\w+) Energy attached)? have no Retreat Cost")
def _(m, d, ab):
    f = slot_filter(m.group(1) + 'Pokémon')
    et = NAME_TO_TYPE.get(m.group(2)) if m.group(2) else None
    return AbilityImpl(kind='passive', hooks={'retreat_cost': lambda g, src, v, slot:
                       0 if slot.owner == src.owner and f(g, slot) and (et is None or g.has_energy_type(slot, et)) else None})


@passive(r"As long as this Pokémon is on your Bench, your Active Pokémon's Retreat Cost is (?:(Colorless(?:Colorless)*)|(\d+)) less")
def _(m, d, ab):
    n = m.group(1).count('Colorless') if m.group(1) else int(m.group(2))
    return AbilityImpl(kind='passive', hooks={'retreat_cost': lambda g, src, v, slot:
                       v - n if not g.is_active(src.slot) and slot.owner == src.owner and g.is_active(slot) else None})


@passive(r"Your opponent's Active (Evolution )?Pokémon's Retreat Cost is (Colorless(?:Colorless)*) more")
def _(m, d, ab):
    evo = bool(m.group(1))
    n = m.group(2).count('Colorless')
    return AbilityImpl(kind='passive', hooks={'retreat_cost': lambda g, src, v, slot:
                       v + n if slot.owner != src.owner and g.is_active(slot) and (not evo or slot.d.stage > 0) else None})


@passive(r"Attacks used by (this Pokémon|your (.*?)Pokémon(?:, except any (.+?))?) do (\d+) more damage to your opponent's Active (.*?)Pokémon(?: for each Prize card your opponent has taken)?")
def _(m, d, ab):
    me_only = m.group(1) == 'this Pokémon'
    f = slot_filter((m.group(2) or '') + 'Pokémon')
    exc = m.group(3)
    n = int(m.group(4))
    tdesc = (m.group(5) or '').strip()
    tf = slot_filter(tdesc + ' Pokémon') if tdesc else (lambda g, s: True)
    per_prize = 'for each Prize card' in m.group(0)
    stack_key = ab.name if 'stack' in ab.text else None

    def h(g, src, dmg, ctx, target):
        a = ctx.attacker
        if a.owner != src.owner:
            return None
        if me_only and a is not src.slot:
            return None
        if not me_only and (not f(g, a) or (exc and a.name == exc)):
            return None
        if tdesc == 'Evolution' and target.d.stage == 0:
            return None
        if tdesc and tdesc != 'Evolution' and not tf(g, target):
            return None
        if stack_key:
            key = ('nostack', stack_key, id(ctx))
            if ctx.data.get(key):
                return None
            ctx.data[key] = True
        return dmg + n * (g.prizes_taken(1 - src.owner) if per_prize else 1)
    return AbilityImpl(kind='passive', hooks={'damage_out': h})


@passive(r"Attacks used by this Pokémon do (\d+) more damage to your opponent's Active Pokémon that has an Ability")
def _(m, d, ab):
    n = int(m.group(1))
    return AbilityImpl(kind='passive', hooks={'damage_out': lambda g, src, dmg, ctx, target:
                       dmg + n if ctx.attacker is src.slot and g.has_ability(target) else None})


@passive(r"As long as this Pokémon is in the Active Spot, attacks used by your opponent's Active Pokémon do (\d+) less damage")
def _(m, d, ab):
    n = int(m.group(1))
    return AbilityImpl(kind='passive', hooks={'damage_out': lambda g, src, dmg, ctx, target:
                       dmg - n if g.is_active(src.slot) and ctx.player != src.owner else None})


@passive(r"This Pokémon gets \+(\d+) HP for each (.+)")
def _(m, d, ab):
    from .compiler import count_expr
    n = int(m.group(1))
    ph = m.group(2).rstrip('.')
    if ph == 'Prize card your opponent has taken':
        cnt = lambda g, s: g.prizes_taken(1 - s.owner)
    else:
        mm = re.match(rf'^({TYPE_WORDS}) Energy attached to it$', ph)
        if not mm:
            raise Unparsed(ph)
        t = NAME_TO_TYPE[mm.group(1)]
        cnt = lambda g, s: g.energy_count(s, t)
    return AbilityImpl(kind='passive', hooks={'hp': lambda g, src, v, slot: v + n * cnt(g, slot) if slot is src.slot else None})


@passive(r"If this Pokémon has (?:any (\w+) Energy attached|(\d+) or more (\w+) Energy attached), it gets \+(\d+) HP")
def _(m, d, ab):
    if m.group(1):
        t1 = m.group(1)
        need = lambda g, s: any(e.d.special_energy for e in s.energy) if t1 == 'Special' else \
            g.has_energy_type(s, NAME_TO_TYPE[t1])
    else:
        k, t = int(m.group(2)), NAME_TO_TYPE[m.group(3)]
        need = lambda g, s: g.energy_count(s, t) >= k
    n = int(m.group(4))
    return AbilityImpl(kind='passive', hooks={'hp': lambda g, src, v, slot: v + n if slot is src.slot and need(g, slot) else None})


@passive(r"As long as this Pokémon is in the Active Spot, your opponent can't play any (Item cards|Stadium cards|Item cards or Pokémon Tool cards) from their hand")
def _(m, d, ab):
    what = m.group(1)

    def h(g, src, player, card):
        if player == src.owner or not g.is_active(src.slot):
            return None
        st = card.d.subtype
        if 'Item' in what and st == 'item':
            return False
        if 'Tool' in what and st == 'tool':
            return False
        if 'Stadium' in what and st == 'stadium':
            return False
    return AbilityImpl(kind='passive', hooks={'can_play': h})


@passive(r"As long as this Pokémon is in play, it is (\w+) and (\w+) type")
def _(m, d, ab):
    ts = [NAME_TO_TYPE[m.group(1)], NAME_TO_TYPE[m.group(2)]]
    return AbilityImpl(kind='passive', hooks={'types': lambda g, src, v, slot: list(ts) if slot is src.slot else None})


@passive(r"If this Pokémon is Knocked Out by damage from an attack from your opponent's Pokémon, search your deck for a card and put it into your hand. Then, shuffle your deck")
def _(m, d, ab):
    def ev(g, src, slot, owner, by_attack, attacker, dest):
        if slot is src.slot and by_attack:
            yield from lib.search_to_hand(g, owner, lambda c: True, 1, slot.top)
    return AbilityImpl(kind='passive', events={'knocked_out': ev})


@passive(r"If this Pokémon is in the Active Spot and is Knocked Out by damage from an attack from your opponent's Pokémon, put (\d+) damage counters on the Attacking Pokémon")
def _(m, d, ab):
    n = int(m.group(1))

    def ev(g, src, slot, owner, by_attack, attacker, dest):
        if slot is src.slot and by_attack and attacker is not None and g.in_play(attacker):
            g.place_counters(attacker, n, 'ability', by=owner)
    return AbilityImpl(kind='passive', events={'knocked_out': ev}, self_ko=False)


# ===================================================================== ativadas (padrões)
ACT = re.compile(r'^(?P<cost>You must (?P<costtxt>.+?) in order to use this Ability\. )?'
                 r'(?P<freq>Once during your turn|As often as you like during your turn)'
                 r'(?:, if (?P<cond>.+?))?,? you may (?:(?P<cost2>.+?) in order to use this Ability\. |use this Ability\. )?'
                 r'(?P<body>.+)$')
ON_BENCH = re.compile(r'^(?:When you play this Pokémon from your hand onto your Bench during your turn, you may '
                      r'|Once during your turn, when you play this Pokémon from your hand onto your Bench, you may use this Ability\. )(?P<body>.+)$')
ON_EVOLVE = re.compile(r'^(?:When you play this Pokémon from your hand to evolve 1 of your Pokémon during your turn, you may '
                       r'|Once during your turn, when you play this Pokémon from your hand to evolve 1 of your Pokémon, '
                       r'(?:if (?P<cond>.+?), )?you may (?:use this Ability\. )?)(?P<body>.+)$')


def _cost(costtxt):
    """'discard a card from your hand' → (can_pay(E), pay(E))"""
    c = costtxt.strip()
    m = re.match(r'^discard (\w+) (?:other )?cards? from your hand$', c)
    if m:
        n = lib.num(m.group(1))
        return (lambda E: len(E.me.hand) >= n,
                lambda E: E.g.discard_from_hand(E.p, n, source=E.card))
    m = re.match(r'^discard an? (.+? card) from your hand$', c)
    if m:
        f = lib.card_filter(m.group(1))
        return (lambda E: any(f(x) for x in E.me.hand),
                lambda E: E.g.discard_from_hand(E.p, 1, source=E.card, pred=f))
    m = re.match(r'^discard a (.+? Energy) from this Pokémon$', c)
    if m:
        f = lib.card_filter(m.group(1))
        return (lambda E: any(f(x) for x in E.slot.energy),
                lambda E: lib.discard_energy_from(E.g, E.p, E.slot, 1, f, None, E.card))
    if c == 'put a card from your hand on the bottom of your deck':
        def pay(E):
            got = yield from E.g.choose_cards(E.p, E.me.hand, 1, 1, 'bottom', 'Carta para o fundo do baralho', E.card)
            for x in got:
                E.me.hand.remove(x)
                E.me.deck.append(x)
        return (lambda E: len(E.me.hand) >= 1, pay)
    m = re.match(r'^discard a (.+?) card from your hand$', c)
    if m:
        f = lib.card_filter(m.group(1))
        return (lambda E: any(f(x) for x in E.me.hand),
                lambda E: E.g.discard_from_hand(E.p, 1, source=E.card, pred=f))
    raise Unparsed(f'custo: {c}')


def _ability_cond(ph):
    ph = ph.strip()
    if ph == 'you have no cards in your hand':
        return lambda E: not E.me.hand
    m = re.match(r"^this Pokémon's remaining HP is (\d+) or less$", ph)
    if m:
        n = int(m.group(1))
        return lambda E: E.g.hp_left(E.slot) <= n
    m = re.match(r'^you played (.+?) from your hand this turn$', ph)
    if m:
        nm = m.group(1)
        return lambda E: nm in E.me.played
    m = re.match(r'^(.+) is in play$', ph)
    if m and m.group(1)[0].isupper() and 'Pokémon' not in m.group(1):
        nm = m.group(1)
        return lambda E: E.g.stadium is not None and E.g.stadium.name == nm
    m = re.match(r'^your Active Pokémon has the (.+) Ability$', ph)
    if m:
        nm = m.group(1)
        return lambda E: E.me.active is not None and any(a.name == nm for a in E.me.active.d.abilities)
    m = re.match(r'^you have (.+?) and (.+?) in play$', ph)
    if m and 'Pokémon' not in ph:
        a, b = m.group(1), m.group(2)
        return lambda E: {a, b} <= {s.name for s in E.me.in_play()}
    m = re.match(r'^(.+?), and if (.+)$', ph)
    if m:
        c1, c2 = _ability_cond(m.group(1)), _ability_cond(m.group(2))
        return lambda E: c1(E) and c2(E)
    if ph.startswith('this Pokémon is'):
        c = cond_expr(ph)
        return c
    return cond_expr(ph)


def _feasible(body):
    """Condição mínima para a habilidade fazer algo (evita opções inúteis)."""
    b = body
    m = re.match(r'^(?:you may )?attach (?:a|an|up to \d+) (.+? card)s? from your hand', b, re.I)
    if m:
        f = lib.card_filter(m.group(1))
        return lambda E: any(f(x) for x in E.me.hand)
    m = re.match(r'^(?:you may )?attach (?:a|an|up to \d+) (.+? card)s? from your discard pile', b, re.I)
    if m:
        f = lib.card_filter(m.group(1))
        return lambda E: any(f(x) for x in E.me.discard)
    if re.match(r'^(?:you may )?(draw|search your deck|look at the top)', b, re.I):
        return lambda E: bool(E.me.deck)
    if re.match(r'^(?:you may )?heal', b, re.I):
        return lambda E: any(s.damage > 0 for s in E.me.in_play())
    return lambda E: True


def compile_ability(d, ab) -> AbilityImpl:
    try:
        return _compile_ability(d, ab)
    except Unparsed as e:
        return AbilityImpl(kind='passive', status='missing', note=str(e))


def _compile_ability(d, ab) -> AbilityImpl:
    t = _clean(ab.text)
    for rx, builder in PASSIVES:
        m = rx.match(t)
        if m:
            try:
                return builder(m, d, ab)
            except Unparsed:
                break
    shared = None
    m = re.search(r"\s*You can't use more than 1 (.+?) Ability (?:each turn|during your turn)\.?$", t)
    m2 = re.search(r"\s*You can't use more than 1 Ability that has \"(.+?)\" in its name each turn\.?$", t)
    if m2:
        shared = m2.group(1)
        t = t[:m2.start()].strip()
    elif m:
        shared = m.group(1).strip('"')
        t = t[:m.start()].strip()
    self_ko = False
    if re.search(r'If you use this Ability, this Pokémon is Knocked Out\.?$', t):
        self_ko = True
        t = re.sub(r'\s*If you use this Ability, this Pokémon is Knocked Out\.?$', '', t)
    ends_turn = False
    if re.search(r'If you use this Ability, your turn ends\.?$', t):
        ends_turn = True
        t = re.sub(r'\s*If you use this Ability, your turn ends\.?$', '', t)

    kind = None
    m = ON_BENCH.match(t)
    cond = None
    cost = None
    once = True
    if m:
        kind, body = 'on_bench', m.group('body')
    else:
        m = ON_EVOLVE.match(t)
        if m:
            kind, body = 'on_evolve', m.group('body')
            if m.group('cond'):
                cond = _ability_cond(m.group('cond'))
        else:
            m = ACT.match(t)
            if m:
                kind, body = 'activated', m.group('body')
                once = m.group('freq').startswith('Once')
                if m.group('cond'):
                    cond = _ability_cond(m.group('cond'))
                ct = m.group('costtxt') or m.group('cost2')
                if ct:
                    cost = _cost(ct)
    if kind is None:
        return AbilityImpl(kind='passive', status='missing', note=t)
    body = body[0].upper() + body[1:]
    prog = compile_text(body)
    feasible = _feasible(body)
    run_body = steps_runner(prog, 'ability')

    def can_use(g, p, slot):
        E = Exec(g, p, slot=slot)
        if cond is not None and not cond(E):
            return False
        if cost is not None and not cost[0](E):
            return False
        return feasible(E)

    def run_all(g, p, slot):
        E = Exec(g, p, slot=slot)
        if cost is not None:
            yield from run(cost[1](E))
        yield from run(run_body(g, p, slot))
        if self_ko and g.in_play(slot):
            slot.damage = max(slot.damage, g.hp(slot))
            yield from g._resolve_kos()
        if ends_turn:
            g.turn_ended = True

    st = prog.status if not prog.unparsed else ('partial' if (prog.pre or prog.post) else 'missing')
    return AbilityImpl(kind=kind, can_use=can_use, run=run_all, once_per_turn=once, shared_key=shared,
                       self_ko=self_ko, status=st, note='; '.join(prog.unparsed))


# ===================================================================== escritas à mão
def _src_active(g, src):
    return g.is_active(src.slot)


@ability('Teal Dance')
def _(d, ab):
    def run_(g, p, s):
        c = next(x for x in g.players[p].hand if x.d.basic_energy and x.d.provides == 'G')
        g.players[p].hand.remove(c)
        yield from g.attach_energy(p, c, s)
        g.draw(p, 1)
    return AbilityImpl(can_use=lambda g, p, s: any(x.d.basic_energy and x.d.provides == 'G' for x in g.players[p].hand),
                       run=run_)


@ability('Recon Directive')
def _(d, ab):
    def run_(g, p, s):
        yield from lib.look_top(g, p, 2, lambda c: True, 1, rest='bottom', source=s.top, min_take=1)
    return AbilityImpl(can_use=lambda g, p, s: bool(g.players[p].deck), run=run_)


@ability('Adrena-Brain')
def _(d, ab):
    def can(g, p, s):
        return g.has_energy_type(s, 'D') and any(x.damage > 0 for x in g.players[p].in_play()) and \
            g.allowed('damage_counters_movable')

    def run_(g, p, s):
        pl, op = g.players[p], g.players[1 - p]
        src = yield from g.choose_slot(p, [x for x in pl.in_play() if x.damage > 0], 'move_from',
                                       'Mover contadores de qual Pokémon seu?', s.top)
        dst = yield from g.choose_slot(p, op.in_play(), 'counters', 'Para qual Pokémon do oponente?', s.top)
        maxn = min(3, src.damage // 10)
        opts = [__import__('ptcg.core', fromlist=['Option']).Option(f'{k} contador(es)', k, 'text')
                for k in range(maxn, 0, -1)]
        opt = yield from g.ask(p, 'amount', 'Quantos contadores mover?', opts, s.top)
        k = opt.value
        if g.anyhook('prevent_counters', target=dst, kind='ability', by=p):
            return
        src.damage -= 10 * k
        dst.damage += 10 * k
        g.say(f'{k} contador(es) movido(s) de {src.name} para {dst.name}')
    return AbilityImpl(can_use=can, run=run_)


@ability('Run Away Draw')
def _(d, ab):
    def run_(g, p, s):
        if g.draw(p, 3):
            g.remove_slot(s, to='deck')
            yield from g._promote_if_needed()
    return AbilityImpl(can_use=lambda g, p, s: bool(g.players[p].deck), run=run_)


@ability('ACE Nullifier')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'can_play': lambda g, src, player, card:
                       False if player != src.owner and card.d.ace_spec and src.slot.tools else None})


@ability('Watchful Eye')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'damage_counters_movable': lambda g, src: False})


@ability('Fairy Zone')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'weakness': lambda g, src, v, slot:
                       ('P', 2) if slot.owner != src.owner and 'N' in slot.d.types else None})


@ability('Wild Growth')
def _(d, ab):
    def h(g, src, units, slot, card):
        if slot.owner == src.owner and card.d.basic_energy and card.d.provides == 'G' and len(units) == 1:
            return [frozenset({'G'}), frozenset({'G'})]
    return AbilityImpl(kind='passive', hooks={'energy_units': h})


@ability('Rapid Vernier')
def _(d, ab):
    def run_(g, p, s):
        pl = g.players[p]
        if pl.active is None or s not in pl.bench:
            return
        yield from g.switch_active(p, s)
        if any(x.energy for x in pl.in_play() if x is not s):
            yield from lib.move_energy(g, p, lambda: [x for x in pl.in_play() if x is not s], lambda: [s], 99,
                                       source=s.top)
    return AbilityImpl(kind='on_bench', run=run_)


@ability('Subjugating Chains')
def _(d, ab):
    def cands(g, p):
        return [x for x in g.players[p].bench if g.has_type(x, 'D') and x.name != 'Pecharunt ex']

    def run_(g, p, s):
        t = yield from g.choose_slot(p, cands(g, p), 'switch', 'Novo Ativo (será Envenenado)', s.top)
        yield from g.switch_active(p, t)
        g.add_condition(t, 'poisoned')
    return AbilityImpl(can_use=lambda g, p, s: bool(cands(g, p)) and g.players[p].active is not None, run=run_,
                       shared_key='Subjugating Chains')


@ability('Sinister Surge')
def _(d, ab):
    def run_(g, p, s):
        pl = g.players[p]
        targets = [x for x in pl.bench if g.has_type(x, 'D')]
        e = next((c for c in pl.deck if c.d.basic_energy and c.d.provides == 'D'), None)
        if e is None or not targets:
            g.shuffle(p)
            return
        t = yield from g.choose_slot(p, targets, 'attach_target', 'Ligar Energia Escuridão em', s.top)
        pl.deck.remove(e)
        yield from g.attach_energy(p, e, t)
        g.shuffle(p)
        g.place_counters(t, 2, 'ability', by=p)
    return AbilityImpl(can_use=lambda g, p, s: any(g.has_type(x, 'D') for x in g.players[p].bench) and
                       any(c.d.basic_energy and c.d.provides == 'D' for c in g.players[p].deck), run=run_)


@ability('Attract Customers')
def _(d, ab):
    def run_(g, p, s):
        yield from lib.look_top(g, p, 6, lambda c: c.d.is_supporter, 1, source=s.top)
    return AbilityImpl(can_use=lambda g, p, s: g.is_active(s) and bool(g.players[p].deck), run=run_)


@ability('Festival Lead')
def _(d, ab):
    return AbilityImpl(kind='passive', hooks={'attack_twice': lambda g, src, slot:
                       slot is src.slot and g.stadium is not None and g.stadium.name == 'Festival Grounds'})


@ability('Psychic Draw')
def _(d, ab):
    import re as _re
    n = int(_re.search(r'Draw (\d+) cards', ab.text).group(1))
    return AbilityImpl(kind='on_evolve', run=lambda g, p, s: g.draw(p, n),
                       can_use=lambda g, p, s: bool(g.players[p].deck))


@ability('Spiteful Evolution')
def _(d, ab):
    def opts(g, p, s):
        return [c for c in g.players[p].hand if c.d.is_evolution and c.d.evolves_from == s.name]

    def run_(g, p, s):
        c = yield from g.choose_cards(p, opts(g, p, s), 1, 1, 'pick', 'Evoluir com', s.top)
        g.players[p].hand.remove(c[0])
        yield from g.evolve(p, s, c[0], from_hand=True)
        g.place_counters(s, 2, 'ability', by=p)
    return AbilityImpl(can_use=lambda g, p, s: not g.first_turn(p) and bool(opts(g, p, s)), run=run_)


@ability('Freezing Shroud')
def _(d, ab):
    def ev(g, src):
        for q in (0, 1):
            for s in g.players[q].in_play():
                if s.name != 'Froslass' and g.has_ability(s):
                    g.place_counters(s, 1, 'ability', by=src.owner)
    return AbilityImpl(kind='passive', events={'checkup': ev})
