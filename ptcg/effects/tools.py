"""Ferramentas Pokémon."""
from __future__ import annotations

from ..core import AttackDef, AttackImpl, TrainerImpl
from . import lib, register_trainer


def tool(name, **kw):
    return register_trainer(name, TrainerImpl(**kw))


def on(src, slot):
    return slot is src.slot


def opp_attack(src, ctx):
    return ctx.player != src.owner


def discard_tool(g, src):
    s, t = src.slot, src.card
    if s is not None and t in s.tools:
        s.tools.remove(t)
        g.players[t.owner].discard.append(t)
        g.say(f'{t.name} foi descartado')


def active_damaged(handler):
    """Gatilho 'se este Pokémon estiver no Ativo e for danificado por ataque do oponente'."""
    def ev(g, src, ctx, slot, damage):
        if slot is src.slot and ctx.player != src.owner and g.is_active(slot):
            return handler(g, src, ctx, slot, damage)
    return ev


# --- dano causado
def plus_vs(n, pred_target, pred_attacker=lambda g, s: True):
    return lambda g, src, dmg, ctx, target: dmg + n if ctx.attacker is src.slot and pred_target(g, target) \
        and pred_attacker(g, ctx.attacker) else None


tool('Maximum Belt', hooks={'damage_out': plus_vs(50, lambda g, t: t.d.is_ex)})
tool('Brave Bangle', hooks={'damage_out': plus_vs(30, lambda g, t: t.d.is_ex, lambda g, a: not a.d.rule_box)})
tool('Light Ball', hooks={'damage_out': plus_vs(50, lambda g, t: t.d.is_ex, lambda g, a: a.name == 'Pikachu ex')})
tool('Binding Mochi', hooks={'damage_out': plus_vs(40, lambda g, t: True, lambda g, a: 'poisoned' in a.conditions)})
tool('Future Booster Energy Capsule', hooks={
    'damage_out': plus_vs(20, lambda g, t: True, lambda g, a: 'future' in a.d.tags),
    'retreat_cost': lambda g, src, v, slot: 0 if on(src, slot) and 'future' in slot.d.tags else None})
tool("Hop's Choice Band", hooks={
    'damage_out': plus_vs(30, lambda g, t: True, lambda g, a: a.d.family == "Hop's"),
    'attack_cost': lambda g, src, cost, slot, attack: (lambda c: (c.remove('C'), c)[1] if 'C' in c else c)(list(cost))
    if on(src, slot) and slot.d.family == "Hop's" else None})

# --- HP
tool('Hero\'s Cape', hooks={'hp': lambda g, src, v, slot: v + 100 if on(src, slot) else None})
tool("Cynthia's Power Weight", hooks={'hp': lambda g, src, v, slot: v + 70 if on(src, slot) and
                                      slot.d.family == "Cynthia's" else None})
tool('Bravery Charm', hooks={'hp': lambda g, src, v, slot: v + 50 if on(src, slot) and slot.d.stage == 0 else None})


def _clear_on_attach(g, src, player, card):
    if card is src.card and src.slot is not None and 'ancient' in src.slot.d.tags:
        src.slot.clear_conditions()


tool('Ancient Booster Energy Capsule', hooks={
    'hp': lambda g, src, v, slot: v + 60 if on(src, slot) and 'ancient' in slot.d.tags else None,
    'condition_immune': lambda g, src, slot, cond: on(src, slot) and 'ancient' in slot.d.tags},
    events={'trainer_played': _clear_on_attach})

# --- recuo / custo
tool('Air Balloon', hooks={'retreat_cost': lambda g, src, v, slot: v - 2 if on(src, slot) else None})
tool('Rescue Board', hooks={'retreat_cost': lambda g, src, v, slot:
                            (0 if g.hp_left(slot) <= 30 else v - 1) if on(src, slot) else None})
tool('Gravity Gemstone', hooks={'retreat_cost': lambda g, src, v, slot:
                                v + 1 if g.is_active(src.slot) and g.is_active(slot) else None})


def _counter_gain(g, src, cost, slot, attack):
    if on(src, slot) and len(g.players[src.owner].prizes) > len(g.players[1 - src.owner].prizes) and 'C' in cost:
        c = list(cost)
        c.remove('C')
        return c


tool('Counter Gain', hooks={'attack_cost': _counter_gain})


def _sparkling(g, src, cost, slot, attack):
    if not on(src, slot) or 'tera' not in slot.d.tags or not cost:
        return None
    best = None
    for t in dict.fromkeys(cost):
        c = list(cost)
        c.remove(t)
        if g.can_pay(slot, c):
            return c
        best = c
    return best


tool('Sparkling Crystal', hooks={'attack_cost': _sparkling})

# --- dano recebido
for _name, _t in (('Babiri Berry', 'M'), ('Colbur Berry', 'D'), ('Haban Berry', 'N'), ('Occa Berry', 'R'),
                  ('Passho Berry', 'W'), ('Payapa Berry', 'P')):
    def _berry(g, src, dmg, ctx, target, active, _t=_t):
        if target is src.slot and opp_attack(src, ctx) and g.has_type(ctx.attacker, _t):
            ctx.data.setdefault('berries', []).append(src)
            return dmg - 60

    def _berry_after(g, src, ctx):
        for b in ctx.data.get('berries', []):
            if b.card is src.card:
                discard_tool(g, src)
    tool(_name, hooks={'damage_in': _berry}, events={'after_attack': _berry_after})

tool('Sacred Charm', hooks={'damage_in': lambda g, src, dmg, ctx, target, active:
                            dmg - 30 if target is src.slot and opp_attack(src, ctx) and g.has_ability(ctx.attacker) else None})
tool('Thick Scale', hooks={'damage_in': lambda g, src, dmg, ctx, target, active:
                           dmg - 50 if target is src.slot and opp_attack(src, ctx) and g.has_type(target, 'N') and
                           set(g.types(ctx.attacker)) & {'G', 'R', 'W', 'L'} else None})


def _brace(g, src, slot, damage, ctx):
    if slot is src.slot and slot.damage == 0 and ctx.player != src.owner:
        discard_tool(g, src)
        return True


tool('Survival Brace', hooks={'survive': _brace})

# --- gatilhos ao ser danificado
tool('Lucky Helmet', events={'damaged_by_attack': active_damaged(lambda g, src, ctx, slot, d: g.draw(src.owner, 2))})
tool('Adversity Policy', events={'damaged_by_attack': active_damaged(
    lambda g, src, ctx, slot, d: g.draw(src.owner, 3) if g.weakness(slot)[0] in g.types(ctx.attacker) else None)})


def _bomb(n, cond=lambda g, src, ctx, slot, d: True, discard=True):
    def h(g, src, ctx, slot, d):
        if cond(g, src, ctx, slot, d) and g.in_play(ctx.attacker):
            if g.place_counters(ctx.attacker, n, 'other', by=src.owner) and discard:
                discard_tool(g, src)
    return active_damaged(h)


tool('Deluxe Bomb', events={'damaged_by_attack': _bomb(12)})
tool('Punk Helmet', events={'damaged_by_attack': _bomb(4, lambda g, src, ctx, slot, d: g.has_type(slot, 'D'),
                                                      discard=False)})
tool('Tremendous Bomb', events={'damaged_by_attack': _bomb(
    12, lambda g, src, ctx, slot, d: not slot.d.is_mega and ctx.attacker.d.is_mega and d >= 240)})
tool("Team Rocket's Hypnotizer", events={'damaged_by_attack': active_damaged(
    lambda g, src, ctx, slot, d: g.add_condition(ctx.attacker, 'asleep')
    if slot.d.family == "Team Rocket's" and g.in_play(ctx.attacker) else None)})


def _fan(g, src, ctx, slot, d):
    a = ctx.attacker
    opp = g.players[ctx.player]
    if not g.in_play(a) or not a.energy or not opp.bench:
        return
    e = yield from g.choose_cards(src.owner, a.energy, 1, 1, 'pick', 'Handheld Fan: Energia do atacante', src.card)
    t = yield from g.choose_slot(src.owner, opp.bench, 'target', 'Mover para qual Pokémon do Banco dele?', src.card)
    a.energy.remove(e[0])
    t.energy.append(e[0])


tool('Handheld Fan', events={'damaged_by_attack': active_damaged(_fan)})


# --- gatilhos ao ser nocauteado
def _amulet(g, src, slot, owner, by_attack, attacker, dest):
    if slot is src.slot and by_attack:
        yield from lib.search_to_hand(g, owner, lambda c: True, 3, src.card)


tool('Amulet of Hope', events={'knocked_out': _amulet})
tool("Lillie's Pearl", hooks={'prizes': lambda g, src, n, slot, taker, by_attack, attacker:
                              n - 1 if slot is src.slot and by_attack and slot.d.family == "Lillie's" else None})


def _baton(g, src, slot, owner, by_attack, attacker, dest):
    pl = g.players[owner]
    if slot is src.slot and by_attack and slot.d.retreat == 4 and g.is_active(slot) and pl.bench:
        es = [e for e in slot.energy if e.d.basic_energy]
        got = yield from g.choose_cards(owner, es, 3, 0, 'pick', 'Heavy Baton: Energias para mover', src.card,
                                        key=lambda c: c.uid)
        for e in got:
            t = yield from g.choose_slot(owner, pl.bench, 'attach_target', f'Mover {e.name} para', src.card)
            slot.energy.remove(e)
            t.energy.append(e)


tool('Heavy Baton', events={'knocked_out': _baton})


# --- fim de turno
def _powerglass(g, src, player):
    pl = g.players[src.owner]
    if player == src.owner and g.is_active(src.slot) and any(c.d.basic_energy for c in pl.discard):
        if (yield from g.yes_no(src.owner, 'Powerglass: ligar Energia básica do descarte?', source=src.card)):
            yield from lib.attach_from_discard(g, src.owner, lambda c: c.d.basic_energy, 1, lambda: [src.slot],
                                               src.card)


tool('Powerglass', events={'turn_end': _powerglass})


def _tm_discard(g, src, player):
    if player == src.owner:
        discard_tool(g, src)


def _granted(attack_def, only=None):
    """Gancho extra_attacks: o Pokémon com a Ferramenta pode usar o ataque impresso nela."""
    def h(g, src, atks, slot):
        if slot is src.slot and (only is None or only(slot)) and attack_def not in atks:
            return atks + [attack_def]
    return h


def _fluorite_run(g, ctx):
    s = ctx.attacker
    g.discard_energy(s, list(s.energy), ctx)
    for x in g.players[ctx.player].in_play():
        if 'tera' in x.d.tags:
            g.heal(x, 9999)
    if False:
        yield


def _geobuster_run(g, ctx):
    yield from g.main_damage(ctx)
    g.discard_energy(ctx.attacker, list(ctx.attacker.energy), ctx)


_FLUORITE = AttackDef('Fluorite', ['G', 'W', 'P'], 0, '',
                      'Discard all Energy from this Pokémon and heal all damage from each of your Tera Pokémon.',
                      AttackImpl(run=_fluorite_run), 'Technical Machine: Fluorite')
_GEOBUSTER = AttackDef('Geobuster', ['F', 'F', 'F', 'F'], 350, '',
                       'Discard all Energy from this Pokémon.', AttackImpl(run=_geobuster_run), 'Core Memory')

tool('Technical Machine: Fluorite', events={'turn_end': _tm_discard}, hooks={'extra_attacks': _granted(_FLUORITE)})
tool('Core Memory', hooks={'extra_attacks': _granted(_GEOBUSTER, lambda sl: sl.name == 'Mega Zygarde ex')})
tool('Backtrack Badge')   # a nova jogada das moedas está em extra.maybe_reroll (chamada pelos passos de moeda)
