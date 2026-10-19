"""Padrões adicionais do compilador (contagens, condições e frases de ataque) — segunda leva de cobertura.

Importado no fim de compiler.py. As funções `*_fallback` são consultadas por count_expr/cond_expr/
opp_active_pred/self_pred quando nenhuma regra original reconhece a frase.
"""
from __future__ import annotations

import re

from ..core import NAME_TO_TYPE, Option
from ..engine import run
from . import lib
from .compiler import NUMW, Unparsed, _dmg_add, _dmg_set, count_expr, cond_expr, pattern
from .lib import TYPE_WORDS, card_filter, num, or_filter, slot_filter

SLOTS_OF = {
    'this Pokémon': lambda E: [E.slot],
    'all of your Pokémon': lambda E: E.me.in_play(),
    'your Pokémon': lambda E: E.me.in_play(),
    "all of your opponent's Pokémon": lambda E: E.op.in_play(),
    'all Pokémon': lambda E: E.me.in_play() + E.op.in_play(),
    'all of your Benched Pokémon': lambda E: list(E.me.bench),
    "your opponent's Active Pokémon": lambda E: [E.opp_active()] if E.opp_active() else [],
}


def _slots_group(desc):
    desc = desc.strip()
    if desc in SLOTS_OF:
        return SLOTS_OF[desc]
    m = re.match(r'^all of your (.+Pokémon)$', desc)
    if m:
        f = slot_filter(m.group(1))
        return lambda E: [s for s in E.me.in_play() if f(E.g, s)]
    raise Unparsed(desc)


def _name_or_filter(sub):
    """'Rattata' → por nome; "Cynthia's Pokémon" / 'Fighting Pokémon' → slot_filter."""
    if 'Pokémon' in sub:
        f = slot_filter(sub)
        return lambda g, s: f(g, s)
    return lambda g, s: s.name == sub


# ====================================================================== contagens
def count_fallback(ph):
    ph = re.sub(r'\s+', ' ', ph.strip().rstrip('.'))
    if ph == "Colorless in your opponent's Active Pokémon's Retreat Cost":
        return lambda E: E.g.retreat_cost(E.opp_active()) if E.opp_active() else 0
    # Energia (carta) ligada
    m = re.match(rf'^((?:Basic |Special )?(?:(?:{TYPE_WORDS}) )?Energy)(?: cards?)? attached to (.+)$', ph)
    if m:
        kind, where = m.group(1), _slots_group(m.group(2))
        if 'Basic' in kind or 'Special' in kind:
            f = card_filter(kind)
            return lambda E: sum(1 for s in where(E) for e in s.energy if f(e))
        t = None
        for w, code in NAME_TO_TYPE.items():
            if kind.startswith(w + ' '):
                t = code
        return lambda E: sum(E.g.energy_count(s, t) for s in where(E))
    if ph == 'Pokémon Tool attached to all Pokémon':
        return lambda E: sum(len(s.tools) for s in E.me.in_play() + E.op.in_play())
    if ph == 'type of Basic Energy attached to all of your Pokémon':
        return lambda E: len({e.d.provides for s in E.me.in_play() for e in s.energy if e.d.basic_energy})
    # descarte
    m = re.match(r'^Pokémon in your discard pile that has the (.+) attack$', ph)
    if m:
        nm = m.group(1)
        return lambda E: sum(1 for c in E.me.discard if c.d.kind == 'pokemon' and any(a.name == nm for a in c.d.attacks))
    m = re.match(r"^(.+?) in your (opponent's )?discard pile$", ph)
    if m:
        f = card_filter(m.group(1))
        opp = bool(m.group(2))
        return lambda E: sum(1 for c in (E.op if opp else E.me).discard if f(c))
    # Pokémon em jogo
    m = re.match(r'^of your Pokémon in play that has the (.+) attack$', ph)
    if m:
        nm = m.group(1)
        return lambda E: sum(1 for s in E.me.in_play() if any(a.name == nm for a in s.d.attacks))
    m = re.match(r'^damage counter on all of your Benched (.+)$', ph)
    if m:
        f = _name_or_filter(m.group(1))
        return lambda E: sum(s.damage // 10 for s in E.me.bench if f(E.g, s))
    m = re.match(r'^of your Pokémon(?: that has "(.+)" in its name)?(?: that has any damage counters on it)$', ph)
    if m:
        part = m.group(1)
        return lambda E: sum(1 for s in E.me.in_play() if s.damage > 0 and (part is None or part in s.name))
    m = re.match(r'^Pokémon in play that has "(.+?)"(?: or "(.+?)")? in its name$', ph)
    if m:
        parts = [x for x in m.groups() if x]
        return lambda E: sum(1 for s in E.me.in_play() + E.op.in_play() if any(p in s.name for p in parts))
    m = re.match(r'^(.+Pokémon) on your Bench$', ph)
    if m:
        f = slot_filter(m.group(1))
        return lambda E: sum(1 for s in E.me.bench if f(E.g, s))
    if ph in ('Prize card your opponent took during their last turn',):
        return lambda E: sum(n for t, who, n in E.g.prize_log if who == E.opp and t == E.g.turn - 1)
    # cartas reveladas / descartadas pelo próprio efeito
    m = re.match(r'^(.+?) (?:cards? )?you find there(?: that has the (.+) attack)?$', ph)
    if m:
        f = card_filter(m.group(1))
        atk = m.group(2)
        return lambda E: sum(1 for c in E.data.get('revealed', []) if f(c) and
                             (atk is None or any(a.name == atk for a in c.d.attacks)))
    m = re.match(r'^(.+?) (?:cards? )?(?:that )?you (?:discarded|revealed) in this way$', ph)
    if m:
        f = card_filter(m.group(1))
        return lambda E: sum(1 for c in E.data.get('discarded_cards', []) if f(c))
    m = re.match(r'^(.+?) you have in play$', ph)
    if m:
        sub = m.group(1)
        if 'Pokémon' in sub:
            f = slot_filter(sub)
            return lambda E: sum(1 for s in E.me.in_play() if f(E.g, s))
        return lambda E: sum(1 for s in E.me.in_play() if s.name == sub)
    raise Unparsed(f'contagem: {ph}')


# ====================================================================== condições
def _same_hand(E):
    return len(E.me.hand) == len(E.op.hand)


def cond_fallback(ph):
    ph = ph.strip()
    m = re.match(r"^you (?:don't|do not) have (.+)$", ph)
    if m:
        c = cond_expr('you have ' + m.group(1))
        return lambda E: not c(E)
    m = re.match(r"^you didn't play (.+?) from your hand during this turn$", ph)
    if m:
        nm = m.group(1)
        return lambda E: nm not in E.me.played
    m = re.match(r"^your opponent (?:doesn't|does not) have (.+)$", ph)
    if m:
        c = cond_expr('your opponent has ' + m.group(1))
        return lambda E: not c(E)
    if ph == 'there is no Stadium in play':
        return lambda E: E.g.stadium is None
    if ph == 'you have no cards in your hand':
        return lambda E: not E.me.hand
    m = re.match(r'^you have exactly (\d+) cards? in your hand$', ph)
    if m:
        n = int(m.group(1))
        return lambda E: len(E.me.hand) == n
    if ph == 'your opponent has exactly 4 cards in their hand':
        return lambda E: len(E.op.hand) == 4
    m = re.match(r'^you have exactly (\d+) Prize cards? remaining$', ph)
    if m:
        n = int(m.group(1))
        return lambda E: len(E.me.prizes) == n
    m = re.match(r'^your opponent has exactly (\d+)(?: or (\d+))? Prize cards? remaining$', ph)
    if m:
        ns = {int(x) for x in m.groups() if x}
        return lambda E: len(E.op.prizes) in ns
    if ph in ('you have the same number of cards in your hand as your opponent',
              'you have the same number of cards in your hand as your opponent has'):
        return _same_hand
    m = re.match(r'^there are (\d+) or fewer cards in your deck$', ph)
    if m:
        n = int(m.group(1))
        return lambda E: len(E.me.deck) <= n
    m = re.match(r'^your opponent has (\d+) or more Benched Pokémon$', ph)
    if m:
        n = int(m.group(1))
        return lambda E: len(E.op.bench) >= n
    m = re.match(r'^you have (\d+) or fewer Benched Pokémon$', ph)
    if m:
        n = int(m.group(1))
        return lambda E: len(E.me.bench) <= n
    m = re.match(r'^you have (\d+) or more (.+? cards?) in your discard pile$', ph)
    if m:
        n, f = int(m.group(1)), card_filter(m.group(2))
        return lambda E: sum(1 for c in E.me.discard if f(c)) >= n
    m = re.match(r'^(.+?) (?:is|are) on your Bench$', ph)
    if m and m.group(1)[0].isupper() and 'Pokémon' not in m.group(1):
        nm = m.group(1)
        return lambda E: any(s.name == nm for s in E.me.bench)
    m = re.match(r'^(.+?) is in your discard pile$', ph)
    if m:
        nm = m.group(1)
        return lambda E: any(c.name == nm for c in E.me.discard)
    m = re.match(r"^the Retreat Cost of your opponent's Active Pokémon is ((?:Colorless)+) or more$", ph)
    if m:
        n = m.group(1).count('Colorless')
        return lambda E: E.opp_active() is not None and E.g.retreat_cost(E.opp_active()) >= n
    m = re.match(r'^this Pokémon used (.+?) during your last turn$', ph)
    if m:
        nm = m.group(1)
        return lambda E: (E.g.turn - 2, nm) in E.slot.flags.get('atk_log', [])
    if ph == "this Pokémon was damaged by an attack during your opponent's last turn":
        return lambda E: any(t == E.g.turn - 1 for t, _ in E.slot.flags.get('dmg_log', []))
    m = re.match(r'^any of your Benched (\w+) have any damage counters on them$', ph)
    if m:
        nm = m.group(1)
        return lambda E: any(s.damage > 0 and s.name == nm for s in E.me.bench)
    if ph == 'all of your Benched Pokémon have at least 1 damage counter on them':
        return lambda E: bool(E.me.bench) and all(s.damage > 0 for s in E.me.bench)
    if ph == 'your opponent has any cards in their discard pile':
        return lambda E: bool(E.op.discard)
    m = re.match(r'^your opponent has any cards in their discard pile that have "(.+)" in the name$', ph)
    if m:
        part = m.group(1)
        return lambda E: any(part in c.name for c in E.op.discard)
    m = re.match(r"^any of your (.+?Pokémon) were Knocked Out by damage from an attack during your opponent's last turn$", ph)
    if m:
        fam = re.match(r"^(.+'s) Pokémon$", m.group(1))
        fam = fam.group(1) if fam else None
        return lambda E: E.g.kod_last_turn(E.p, lambda e: e['by_attack'] and (fam is None or e['family'] == fam))
    if ph == "1 of your other Ancient Pokémon used an attack during your last turn":
        return lambda E: any(t == E.g.turn - 2 and s is not E.slot and 'ancient' in s.d.tags
                             for t, s, _ in E.me.attack_log)
    if ph == "you can't discard 4 cards in this way" or re.match(r"^you can't discard \d+ cards in this way$", ph):
        return lambda E: not E.data.get('did_all')
    if ph == "you can't":
        return lambda E: not E.data.get('did')
    if ph == "you can't discard any":
        return lambda E: not E.data.get('did')
    if ph in ('you discarded any cards in this way', 'you discarded a Pokémon Tool in this way'):
        return lambda E: bool(E.data.get('did'))
    if ph == "this Pokémon and your opponent's Active Pokémon have the same amount of Energy attached":
        return lambda E: E.opp_active() is not None and E.g.energy_count(E.slot) == E.g.energy_count(E.opp_active())
    m = re.match(r'^a Pokémon that has "(.+)" in its name is on your Bench$', ph)
    if m:
        part = m.group(1)
        return lambda E: any(part in s.name for s in E.me.bench)
    m = re.match(r"^this Pokémon's remaining HP is (\d+) or less$", ph)
    if m:
        n = int(m.group(1))
        return lambda E: E.g.hp_left(E.slot) <= n
    if ph == 'your Benched Pokémon have any Shadowy Darkness Energy attached':
        return lambda E: any(e.name == 'Shadowy Darkness Energy' for s in E.me.bench for e in s.energy)
    if ph == 'your opponent has a Stadium in play':
        return lambda E: E.g.stadium is not None and E.g.stadium.owner == E.opp
    if ph == "you have exactly 30 cards in your hand":
        return lambda E: len(E.me.hand) == 30
    raise Unparsed(f'condição: {ph}')


def opp_pred_fallback(d):
    d = d.strip()
    if d in ('has no damage counters on it', 'has no damage counters on it before this attack does damage'):
        return lambda E, s: s.damage == 0
    m = re.match(r'^has exactly (\d+) damage counters on it$', d)
    if m:
        n = int(m.group(1))
        return lambda E, s: s.damage == 10 * n
    if d == "isn't a Pokémon ex":
        return lambda E, s: not s.d.is_ex
    m = re.match(rf'^has (\w+) Resistance$', d)
    if m and m.group(1) in NAME_TO_TYPE:
        t = NAME_TO_TYPE[m.group(1)]
        return lambda E, s: s.d.resistance == t
    if d == 'has no Retreat Cost':
        return lambda E, s: E.g.retreat_cost(s) == 0
    if d == 'is an evolved Pokémon':
        return lambda E, s: s.evolved
    m = re.match(r'^is a (\w+) Pokémon$', d)
    if m and m.group(1) in NAME_TO_TYPE:
        t = NAME_TO_TYPE[m.group(1)]
        return lambda E, s: E.g.has_type(s, t)
    raise Unparsed(f'condição do Ativo: {d}')


def self_pred_fallback(d):
    d = d.strip()
    m = re.match(r'^is (Asleep|Burned|Confused|Paralyzed|Poisoned)(?: or (Asleep|Burned|Confused|Paralyzed|Poisoned))?$', d)
    if m:
        cs = [lib.cond_word(x) for x in m.groups() if x]
        return lambda E, s: any(c in s.conditions for c in cs)
    if d == 'is affected by a Special Condition':
        return lambda E, s: bool(s.conditions)
    m = re.match(r'^has no (.+? Energy) attached$', d)
    if m:
        nm = m.group(1)
        return lambda E, s: not any(e.name == nm for e in s.energy)
    if d == "has more Energy attached than your opponent's Active Pokémon":
        return lambda E, s: E.opp_active() is not None and E.g.energy_count(s) > E.g.energy_count(E.opp_active())
    m = re.match(r"^remaining HP is (\d+) or less$", d)
    if m:
        n = int(m.group(1))
        return lambda E, s: E.g.hp_left(s) <= n
    m = re.match(rf'^has (\d+) or more ({TYPE_WORDS}) Energy attached$', d)
    if m:
        n, t = int(m.group(1)), NAME_TO_TYPE[m.group(2)]
        return lambda E, s: E.g.energy_count(s, t) >= n
    raise Unparsed(f'condição deste Pokémon: {d}')


# ====================================================================== utilidades dos passos
def cap(s):
    s = s.strip()
    return s[0].upper() + s[1:] if s else s


def predicted_ko(E, t=None):
    """O Pokémon `t` (padrão: o Ativo atacado) será Nocauteado por este ataque (dano já aplicado)?"""
    t = t if t is not None else (E.ctx.defender if E.ctx is not None else None)
    return t is not None and E.g.in_play(t) and t.damage >= E.g.hp(t)


def knock_out(E, t):
    """Nocauteia `t` agora (conta como Nocaute por ataque quando vem de um ataque)."""
    if t is None or not E.g.in_play(t):
        return
    if E.ctx is not None:
        if t.owner != E.p and E.g.effects_prevented(E.ctx, t):
            return
        t.flags['hit'] = (E.g.turn, 'attack', E.ctx.attacker)
    t.damage = max(t.damage, E.g.hp(t))
    E.g.say(f'{E.g.slot_label(t)} será Nocauteado')


def use_attack_as_this(E, a):
    """Usa o ataque `a` (de outro Pokémon) como se fosse este ataque."""
    g, ctx = E.g, E.ctx
    ctx.attack = a
    ctx.damage = a.damage
    ctx.no_damage = False
    im = a.impl
    if im is not None:
        ctx.ignore_effects = im.ignore_effects
        ctx.ignore_weakness = im.ignore_weakness
        ctx.ignore_resistance = im.ignore_resistance
    g.say(f'{ctx.attacker.name} usou {a.name} como este ataque')
    if im is not None and im.run is not None:
        yield from run(im.run(g, ctx))
        return
    if im is not None and im.pre is not None:
        yield from run(im.pre(g, ctx))
    if not ctx.no_damage:
        yield from g.main_damage(ctx)
    if im is not None and im.post is not None and not ctx.no_damage:
        yield from run(im.post(g, ctx))


def not_in_copy_chain(E, pool):
    """Tira do pool os ataques que já estão na cadeia de cópias deste ataque. Ex.: Night Joker usa um ataque
    de um N's Pokémon no Banco; o Night Joker de outro N's Zoroark ex não é uma escolha válida (só levaria a
    escolher de novo entre os mesmos ataques), e oferecê-lo deixava o motor repetir a cópia sem fim."""
    if E.ctx is None:
        return pool
    chain = E.ctx.data.setdefault('copy_chain', set())
    chain.add(E.ctx.attack.name)
    return [(s, a) for s, a in pool if a.name not in chain]


def choose_attack(E, pool, text='Usar qual ataque como este ataque?', copy=True):
    """pool: lista de (slot, AttackDef). Devolve o AttackDef escolhido (ou None).
    copy=False quando a escolha não é para usar o ataque (ex.: bloquear um ataque)."""
    if copy:
        pool = not_in_copy_chain(E, pool)
    if not pool:
        return None
    opts = [Option(f'{a.name} ({s.name})', a, 'text') for s, a in pool]
    o = yield from E.g.ask(E.p, 'copy_attack', text, opts, E.card)
    return o.value


# ====================================================================== dano / alvos
def _target_pool(E, bench, extra=None):
    pool = E.op.bench if bench else E.op.in_play()
    return [s for s in pool if extra is None or extra(E, s)]


def _spread_damage(n, k, bench, extra=None, each=False, count=None):
    """Causa n de dano em k alvos escolhidos do oponente (ou em cada um deles)."""
    def step(E):
        E.ctx.no_damage = False
        E.ctx.damage = 0
        total = n * (count(E) if count else 1)
        chosen = []
        for _ in range(k):
            cands = [s for s in _target_pool(E, bench, extra) if s not in chosen]
            if not cands:
                break
            s = yield from E.g.choose_slot(E.p, cands, 'damage_target', f'Causar {total} de dano em', E.card)
            chosen.append(s)
        for s in chosen:
            E.g.deal_attack_damage(E.ctx, s, total)
    step.est = lambda E, d: n * (count(E) if count else 1)
    return step


_SPECIAL_ENERGY = lambda E, s: any(e.d.special_energy for e in s.energy)


@pattern(rf"This attack does (\d+) damage to {NUMW} of your opponent's (Benched )?Pokémon( ex)?( or Benched Pokémon V)?( that has any Special Energy attached| that has any damage counters on it)?", 'pre')
def _(m):
    n, k, bench = int(m.group(1)), num(m.group(2)), bool(m.group(3))
    ex = bool(m.group(4))
    extra = None
    if ex:
        extra = lambda E, s: s.d.is_ex or (m.group(5) and 'v' in s.d.tags)
    if m.group(6) and 'Special' in m.group(6):
        extra = _SPECIAL_ENERGY
    elif m.group(6):
        extra = lambda E, s: s.damage > 0
    return _spread_damage(n, k, bench, extra)


@pattern(rf"This attack does (\d+) damage to {NUMW} of your opponent's (Benched )?Pokémon for each (.+)", 'pre')
def _(m):
    n, k, bench = int(m.group(1)), num(m.group(2)), bool(m.group(3))
    return _spread_damage(n, k, bench, count=count_expr(m.group(4)))


@pattern(rf"This attack does (\d+) damage to each of {NUMW} of your opponent's Pokémon", 'pre')
def _(m):
    n, k = int(m.group(1)), num(m.group(2))
    return _spread_damage(n, k, False)


@pattern(r"This attack does (\d+) damage to each of your opponent's Benched Pokémon", 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        E.ctx.damage = 0
        for s in list(E.op.bench):
            E.g.deal_attack_damage(E.ctx, s, n)
    step.est = lambda E, d: n
    return step


@pattern(r"This attack (?:also )?does (\d+) damage to each (?:of your opponent's )?Benched Pokémon that has any damage counters on it", 'post')
def _(m):
    n = int(m.group(1))
    return lambda E: [E.g.deal_attack_damage(E.ctx, s, n) for s in list(E.op.bench) if s.damage > 0]


@pattern(r"This attack also does (\d+) damage to each Benched Pokémon that has any damage counters on it")
def _(m):
    n = int(m.group(1))

    def step(E):
        for s in list(E.op.bench) + list(E.me.bench):
            if s.damage > 0:
                E.g.deal_attack_damage(E.ctx, s, n)
    return step


@pattern(r"This attack also does (\d+) damage to 1 of your opponent's Benched Pokémon that has any damage counters on it")
def _(m):
    n = int(m.group(1))

    def step(E):
        c = [s for s in E.op.bench if s.damage > 0]
        if c:
            s = yield from E.g.choose_slot(E.p, c, 'bench_target', f'Causar {n} de dano em', E.card)
            E.g.deal_attack_damage(E.ctx, s, n)
    return step


@pattern(r"This attack also does (\d+) damage to each of your opponent's Benched Pokémon for each Prize card your opponent has taken")
def _(m):
    n = int(m.group(1))

    def step(E):
        k = E.g.prizes_taken(E.opp)
        for s in list(E.op.bench):
            E.g.deal_attack_damage(E.ctx, s, n * k)
    return step


@pattern(r"This attack does (\d+) damage to 1 of your opponent's Benched Pokémon for each damage counter on that Pokémon", 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        E.ctx.damage = 0
        c = list(E.op.bench)
        if not c:
            return
        s = yield from E.g.choose_slot(E.p, c, 'bench_target', 'Escolha o alvo', E.card)
        E.g.deal_attack_damage(E.ctx, s, n * (s.damage // 10))
    return step


@pattern(r"This attack does (\d+) damage to 1 of your opponent's Pokémon for each damage counter on that Pokémon", 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        E.ctx.damage = 0
        c = list(E.op.in_play())
        s = yield from E.g.choose_slot(E.p, c, 'damage_target', 'Escolha o alvo', E.card)
        E.g.deal_attack_damage(E.ctx, s, n * (s.damage // 10))
    return step


@pattern(r"This attack does that much more damage", 'pre')
def _(m):
    def step(E):
        E.ctx.damage += sum(d for t, d in E.slot.flags.get('dmg_log', []) if t == E.g.turn - 1)
    return step


@pattern(r"This attack's base damage is (\d+)", 'pre')
def _(m):
    n = int(m.group(1))
    return _dmg_set(lambda E: n)


@pattern(r"During your next turn, this Pokémon's (.+?) attack's base damage is (\d+)")
def _(m):
    name, n = m.group(1), int(m.group(2))

    def step(E):
        s = E.slot
        E.g.add_effect(f'{name} base {n}', E.p, {'damage_out': lambda g, src, dmg, ctx, target, s=s:
                       n if ctx.attacker is s and ctx.attack.name == name and dmg < n else None},
                       target=s, duration='my_next_turn', while_active=True)
    return step


@pattern(r"Your opponent reveals their hand, and this attack does (\d+) damage for each (.+?) you find there", 'pre')
def _(m):
    n = int(m.group(1))
    f = card_filter(m.group(2))

    def step(E):
        lib.reveal_hand(E.g, E.opp)
        E.data['revealed'] = list(E.op.hand)
        E.ctx.damage = n * sum(1 for c in E.op.hand if f(c))
    step.est = lambda E, d: n * sum(1 for c in E.op.hand if f(c))
    return step


@pattern(r"This attack does (\d+) damage for each (.+?) you find there", 'pre')
def _(m):
    n = int(m.group(1))
    cnt = count_expr(m.group(2) + ' you find there')
    return _dmg_set(lambda E: n * cnt(E))


# --- Nocaute direto
@pattern(r"(?:It|That Pokémon|Your opponent's Active Pokémon|The Defending Pokémon) is Knocked Out")
def _(m):
    return lambda E: knock_out(E, E.opp_active())


@pattern(r"Knock Out your opponent's Active Pokémon")
def _(m):
    return lambda E: knock_out(E, E.opp_active())


@pattern(r"Both Active Pokémon are Knocked Out")
def _(m):
    def step(E):
        knock_out(E, E.opp_active())
        E.slot.damage = max(E.slot.damage, E.g.hp(E.slot))
    return step


@pattern(rf"Knock Out {NUMW} of your opponent's Pokémon( that has exactly (\d+) damage counters on it)?")
def _(m):
    exact = int(m.group(3)) if m.group(3) else None

    def step(E):
        c = [s for s in E.op.in_play() if exact is None or s.damage == 10 * exact]
        if not c:
            return
        s = yield from E.g.choose_slot(E.p, c, 'ko_target', 'Nocautear qual Pokémon?', E.card)
        knock_out(E, s)
    return step


@pattern(r"Knock Out each of your opponent's Pokémon that has (\d+) HP or less remaining")
def _(m):
    n = int(m.group(1))

    def step(E):
        for s in list(E.op.in_play()):
            if E.g.hp_left(s) <= n:
                knock_out(E, s)
    return step


@pattern(r"Choose a Pokémon in play that has the least HP remaining, except for this Pokémon, and it is Knocked Out")
def _(m):
    def step(E):
        pool = [s for s in E.me.in_play() + E.op.in_play() if s is not E.slot]
        if not pool:
            return
        least = min(E.g.hp_left(s) for s in pool)
        c = [s for s in pool if E.g.hp_left(s) == least]
        s = yield from E.g.choose_slot(E.p, c, 'ko_target', 'Nocautear qual Pokémon?', E.card)
        knock_out(E, s)
    return step


@pattern(r"If all of them are heads, Knock Out 1 of your opponent's Pokémon")
def _(m):
    def step(E):
        if E.data.get('tails_n', 1) == 0 and E.data.get('heads_n', 0) > 0:
            c = E.op.in_play()
            s = yield from E.g.choose_slot(E.p, c, 'ko_target', 'Nocautear qual Pokémon?', E.card)
            knock_out(E, s)
    return step


# --- copiar ataques
@pattern(r"(?:Choose 1 of your opponent's Active Pokémon's attacks and use it as this attack)")
def _(m):
    def step(E):
        t = E.opp_active()
        if t is None:
            return
        a = yield from choose_attack(E, [(t, x) for x in E.g.attacks_of(t)])
        if a is not None:
            yield from use_attack_as_this(E, a)
    return step


@pattern(r"Choose 1 of your opponent's Active (Tera )?Pokémon's attacks and use it as this attack")
def _(m):
    def step(E):
        t = E.opp_active()
        if t is None or (m.group(1) and 'tera' not in t.d.tags):
            return
        a = yield from choose_attack(E, [(t, x) for x in E.g.attacks_of(t)])
        if a is not None:
            yield from use_attack_as_this(E, a)
    return step


@pattern(r"Choose 1 of your Benched (.+?)Pokémon's attacks and use it as this attack")
def _(m):
    f = slot_filter(m.group(1) + 'Pokémon')

    def step(E):
        pool = [(s, a) for s in E.me.bench if f(E.g, s) for a in E.g.attacks_of(s)]
        a = yield from choose_attack(E, pool)
        if a is not None:
            yield from use_attack_as_this(E, a)
    return step


@pattern(r"Choose an attack from 1 of your opponent's Pokémon in play and use it as this attack")
def _(m):
    def step(E):
        pool = [(s, a) for s in E.op.in_play() for a in E.g.attacks_of(s)]
        a = yield from choose_attack(E, pool)
        if a is not None:
            yield from use_attack_as_this(E, a)
    return step


@pattern(r"If you have no cards in your hand, choose an attack from 1 of your opponent's Pokémon in play and use it as this attack")
def _(m):
    def step(E):
        if E.me.hand:
            return
        pool = [(s, a) for s in E.op.in_play() for a in E.g.attacks_of(s)]
        a = yield from choose_attack(E, pool)
        if a is not None:
            yield from use_attack_as_this(E, a)
    return step


@pattern(r"Reveal the top (\d+) cards of your opponent's deck")
def _(m):
    n = int(m.group(1))

    def step(E):
        E.data['revealed'] = list(E.op.deck[:n])
        E.g.say(f'Reveladas: {", ".join(c.name for c in E.data["revealed"])}')
    return step


@pattern(r"You may choose an attack from a Pokémon you find there and use it as this attack")
def _(m):
    def step(E):
        pool = not_in_copy_chain(E, [(c, a) for c in E.data.get('revealed', []) if c.d.kind == 'pokemon'
                                     for a in c.d.attacks])
        if not pool:
            return
        opts = [Option(f'{a.name} ({c.name})', a, 'text') for c, a in pool]
        opts.append(Option('Não usar nenhum', None, 'text'))
        o = yield from E.g.ask(E.p, 'copy_attack', 'Usar qual ataque como este ataque?', opts, E.card)
        if o.value is not None:
            yield from use_attack_as_this(E, o.value)
    return step


@pattern(r"Shuffle the revealed cards into your opponent's deck")
def _(m):
    return lambda E: E.g.shuffle(E.opp)


@pattern(r"Discard the top card of your deck, and if that card is a Supporter card, use the effect of that card as the effect of this attack")
def _(m):
    def step(E):
        got = lib.mill(E.g, E.p, 1)
        if got and got[0].d.is_supporter and got[0].d.impl is not None and got[0].d.impl.run is not None:
            yield from run(got[0].d.impl.run(E.g, E.p, got[0]))
    return step


# ====================================================================== descartes da mão / baralho
@pattern(rf"(?:You may )?[Dd]iscard (up to {NUMW}|any number of|{NUMW}) (.+?) from your hand", 'pre')
def _(m):
    q = m.group(1)
    upto = q.startswith('up to') or q == 'any number of' or m.group(0).startswith('You may')
    n = 99 if q == 'any number of' else num(q.replace('up to ', ''))
    pred = card_filter(m.group(4))

    def step(E):
        cands = [c for c in E.me.hand if pred(c)]
        E.data['did'] = False
        E.data['did_all'] = False
        E.data['discarded'] = 0
        E.data['discarded_cards'] = []
        if not upto and len(cands) < n:
            return
        got = yield from E.g.choose_cards(E.p, cands, min(n, len(cands)), 0 if upto else n, 'discard',
                                          'Cartas da mão para descartar', E.card)
        for c in got:
            E.me.hand.remove(c)
        E.g.discard_cards(got)
        E.data.update(did=bool(got), did_all=len(got) >= n or (upto and bool(got)), discarded=len(got),
                      discarded_cards=list(got))
    step.est = lambda E, d: (E.data.update(discarded=min(n if n < 99 else 4, sum(1 for c in E.me.hand if pred(c)))) or d)
    return step


@pattern(r"You may discard your hand", 'pre')
def _(m):
    def step(E):
        E.data['did'] = False
        if E.me.hand and (yield from E.g.yes_no(E.p, 'Descartar sua mão?', source=E.card)):
            E.data['discarded'] = len(E.me.hand)
            E.g.discard_hand(E.p)
            E.data['did'] = True
    return step


@pattern(r"If you discarded any cards in this way, this attack does (\d+) more damage", 'pre')
def _(m):
    n = int(m.group(1))
    return _dmg_add(lambda E: n if E.data.get('did') else 0)


@pattern(r"Discard (a|\d+) (Fire Energy), (a) (Water Energy), and (a) (Lightning Energy) from this Pokémon")
def _(m):
    def step(E):
        for t in ('Fire', 'Water', 'Lightning'):
            code = NAME_TO_TYPE[t]
            yield from lib.discard_energy_from(E.g, E.p, E.slot, 1, lambda e, code=code: e.d.provides == code,
                                               E.ctx, E.card)
    return step


@pattern(rf"Discard (up to {NUMW}|{NUMW}) ({TYPE_WORDS}|Basic|Special)? ?Energy(?: cards?)? from this Pokémon")
def _(m):
    q = m.group(1)
    n = num(q.replace('up to ', ''))
    t = m.group(4)
    pred = None
    if t in NAME_TO_TYPE:
        code = NAME_TO_TYPE[t]
        pred = lambda e, code=code: e.d.provides == code
    elif t == 'Basic':
        pred = lambda e: e.d.basic_energy

    def step(E):
        yield from lib.discard_energy_from(E.g, E.p, E.slot, n, pred, E.ctx, E.card, units=not q.startswith('up to'))
    return step


@pattern(r"Discard a Team Rocket's Energy from this Pokémon")
def _(m):
    def step(E):
        got = yield from lib.discard_energy_from(E.g, E.p, E.slot, 1, lambda e: e.name == "Team Rocket's Energy",
                                                 E.ctx, E.card)
        E.data['did'] = bool(got)
    return step


@pattern(r"Discard (?:all|up to \d+) ({0}) Energy from this Pokémon".format(TYPE_WORDS))
def _(m):
    code = NAME_TO_TYPE[m.group(1)]
    allx = m.group(0).startswith('Discard all')
    k = 99 if allx else int(re.search(r'up to (\d+)', m.group(0)).group(1))

    def step(E):
        pool = [e for e in E.slot.energy if e.d.provides == code]
        if allx:
            got = E.g.discard_energy(E.slot, pool, E.ctx)
        else:
            got = yield from lib.discard_energy_from(E.g, E.p, E.slot, k, lambda e: e.d.provides == code, E.ctx, E.card)
        E.data['discarded'] = len(got)
    return step


@pattern(r"Discard any amount of ({0}) Energy from among your Pokémon".format(TYPE_WORDS))
def _(m):
    code = NAME_TO_TYPE[m.group(1)]

    def step(E):
        pool = [(s, e) for s in E.me.in_play() for e in s.energy if e.d.provides == code]
        where = {e.uid: s for s, e in pool}
        got = yield from E.g.choose_cards(E.p, [e for _, e in pool], len(pool), 0, 'discard_energy_any',
                                          'Energias a descartar', E.card, key=lambda e: (where[e.uid].sid, e.d.id),
                                          labeler=lambda e: f'{e.name} — {E.g.slot_label(where[e.uid])}')
        for e in got:
            E.g.discard_energy(where[e.uid], [e], E.ctx)
        E.data['discarded'] = len(got)
        E.data['discarded_cards'] = list(got)
    step.est = lambda E, d: (E.data.update(discarded=sum(1 for s in E.me.in_play() for e in s.energy
                                                          if e.d.provides == code)) or d)
    return step


@pattern(r"Discard all Pokémon Tools and Special Energy from (?:all of )?your opponent's (Active )?Pokémon")
def _(m):
    active_only = bool(m.group(1))

    def step(E):
        for s in ([E.opp_active()] if active_only else list(E.op.in_play())):
            if s is None or E.g.effects_prevented(E.ctx, s):
                continue
            tools, s.tools = s.tools, []
            E.g.discard_cards(tools)
            E.g.discard_energy(s, [e for e in s.energy if e.d.special_energy])
    return step


@pattern(r"Discard all Special Energy from all of your opponent's Pokémon")
def _(m):
    def step(E):
        for s in list(E.op.in_play()):
            if not E.g.effects_prevented(E.ctx, s):
                E.g.discard_energy(s, [e for e in s.energy if e.d.special_energy])
    return step


@pattern(r"Before doing damage, discard all Pokémon Tools and Special Energy from your opponent's Active Pokémon", 'pre')
def _(m):
    def step(E):
        s = E.opp_active()
        if s is None or E.g.effects_prevented(E.ctx, s):
            return
        tools, s.tools = s.tools, []
        E.g.discard_cards(tools)
        E.g.discard_energy(s, [e for e in s.energy if e.d.special_energy])
    return step


@pattern(r"Before doing damage, discard all Pokémon Tools from this Pokémon", 'pre')
def _(m):
    def step(E):
        tools, E.slot.tools = E.slot.tools, []
        E.data['did'] = bool(tools)
        E.g.discard_cards(tools)
    return step


@pattern(r"If you can't discard any, this attack does nothing", 'pre')
def _(m):
    def step(E):
        if not E.data.get('did'):
            E.ctx.no_damage = True
            E.ctx.damage = 0
    return step


@pattern(r"Discard up to (\d+) Pokémon Tools from your opponent's Pokémon")
def _(m):
    n = int(m.group(1))

    def step(E):
        for _ in range(n):
            pool = [(s, t) for s in E.op.in_play() for t in s.tools if not E.g.effects_prevented(E.ctx, s)]
            if not pool:
                break
            where = {t.uid: s for s, t in pool}
            got = yield from E.g.choose_cards(E.p, [t for _, t in pool], 1, 0, 'pick', 'Ferramenta a descartar',
                                              E.card, labeler=lambda t: f'{t.name} — {E.g.slot_label(where[t.uid])}')
            if not got:
                break
            where[got[0].uid].tools.remove(got[0])
            E.g.discard_cards(got)
    return step


@pattern(r"(?:You may )?[Dd]iscard (?:up to )?(\d+) (?:Basic )?Energy(?: cards?)? from your Benched Pokémon", 'pre')
def _(m):
    n = int(m.group(1))
    basic = 'Basic' in m.group(0)

    def step(E):
        pool = [(s, e) for s in E.me.bench for e in s.energy if e.d.basic_energy or not basic]
        where = {e.uid: s for s, e in pool}
        got = yield from E.g.choose_cards(E.p, [e for _, e in pool], min(n, len(pool)), 0, 'discard_energy_any',
                                          'Energias a descartar', E.card, key=lambda e: (where[e.uid].sid, e.d.id),
                                          labeler=lambda e: f'{e.name} — {E.g.slot_label(where[e.uid])}')
        for e in got:
            E.g.discard_energy(where[e.uid], [e], E.ctx)
        E.data['discarded'] = len(got)       # ruling 2340: "+dano por carta descartada" (Erasure Ball, Flashing Spear)
    return step


@pattern(r"Discard up to (\d+) ({0}) Energy from your Pokémon".format(TYPE_WORDS))
def _(m):
    n, code = int(m.group(1)), NAME_TO_TYPE[m.group(2)]

    def step(E):
        pool = [(s, e) for s in E.me.in_play() for e in s.energy if e.d.provides == code]
        where = {e.uid: s for s, e in pool}
        got = yield from E.g.choose_cards(E.p, [e for _, e in pool], min(n, len(pool)), 0, 'discard_energy_any',
                                          'Energias a descartar', E.card, key=lambda e: (where[e.uid].sid, e.d.id),
                                          labeler=lambda e: f'{e.name} — {E.g.slot_label(where[e.uid])}')
        for e in got:
            E.g.discard_energy(where[e.uid], [e], E.ctx)
    return step


@pattern(rf"Discard up to {NUMW} ({TYPE_WORDS}) Energy cards? from your Pokémon")
def _(m):
    n, code = num(m.group(1)), NAME_TO_TYPE[m.group(2)]

    def step(E):
        pool = [(s, e) for s in E.me.in_play() for e in s.energy if e.d.provides == code]
        where = {e.uid: s for s, e in pool}
        got = yield from E.g.choose_cards(E.p, [e for _, e in pool], min(n, len(pool)), 0, 'discard_energy_any',
                                          'Energias a descartar', E.card, key=lambda e: (where[e.uid].sid, e.d.id),
                                          labeler=lambda e: f'{e.name} — {E.g.slot_label(where[e.uid])}')
        for e in got:
            E.g.discard_energy(where[e.uid], [e], E.ctx)
    return step


@pattern(r"Discard the top (\d+) cards of your deck and put 1 of them into your hand")
def _(m):
    n = int(m.group(1))

    def step(E):
        cards = lib.mill(E.g, E.p, n)
        if cards:
            got = yield from E.g.choose_cards(E.p, cards, 1, 1, 'pick', 'Carta para a mão', E.card, key=lambda c: c.d.id)
            for c in got:
                E.me.discard.remove(c)
                E.me.hand.append(c)
    return step


@pattern(r"Discard the top (\d+) cards of your deck, and this attack does (\d+) (more )?damage for each (.+?) (?:that )?you discarded in this way", 'pre')
def _(m):
    n, dmg, more = int(m.group(1)), int(m.group(2)), bool(m.group(3))
    f = card_filter(m.group(4))

    def step(E):
        cards = lib.mill(E.g, E.p, n)
        k = sum(1 for c in cards if f(c))
        if more:
            E.ctx.damage += dmg * k
        else:
            E.ctx.damage = dmg * k
    step.est = lambda E, d: d
    return step


@pattern(r"Discard the bottom card of your deck")
def _(m):
    def step(E):
        E.data['did'] = False
        if E.me.deck:
            c = E.me.deck.pop()
            E.me.discard.append(c)
            E.g.say(f'Descartou o fundo do baralho: {c.name}')
            E.data['did'] = True
    return step


@pattern(r"Discard all cards from this Pokémon and put this Pokémon on top of your deck")
def _(m):
    def step(E):
        s = E.slot
        top = s.top
        cards = E.g.remove_slot(s, to='discard')
        E.me.discard.remove(top)
        E.me.deck.insert(0, top)
    return step


@pattern(r"Draw (\d+) cards from the bottom of your deck")
def _(m):
    n = int(m.group(1))

    def step(E):
        for _ in range(n):
            if E.me.deck:
                E.me.hand.append(E.me.deck.pop())
    return step


@pattern(r"Discard the top card of each player's deck")
def _(m):
    def step(E):
        lib.mill(E.g, E.p, 1)
        lib.mill(E.g, E.opp, 1)
    return step


@pattern(r"Search your deck for up to (\d+) Basic ({0}) Energy cards and discard them".format(TYPE_WORDS))
def _(m):
    n, code = int(m.group(1)), NAME_TO_TYPE[m.group(2)]

    def step(E):
        found = yield from E.g.search_deck(E.p, lambda c: c.d.basic_energy and c.d.provides == code, n, 'search',
                                           'Energias para descartar', E.card)
        E.g.discard_cards(found)
    return step


@pattern(r"Search your deck for a card\. Shuffle your deck, then put that card on top of it|Search your deck for a card")
def _(m):
    def step(E):
        found = yield from E.g.search_deck(E.p, lambda c: True, 1, 'search', 'Carta para o topo do baralho', E.card)
        E.g.shuffle(E.p)
        for c in found:
            E.me.deck.insert(0, c)
    return step


@pattern(r"Shuffle your deck, then put that card on top of it")
def _(m):
    return None


@pattern(r"Search your deck for 2 cards, shuffle your deck, then put those cards on top of it in any order")
def _(m):
    def step(E):
        found = yield from E.g.search_deck(E.p, lambda c: True, 2, 'search', 'Cartas para o topo do baralho', E.card,
                                           min_n=min(2, len(E.me.deck)))
        E.g.shuffle(E.p)
        if len(found) == 2:
            E.me.limbo.extend(found)
            o = yield from E.g.ask(E.p, 'order', 'Qual fica no topo?',
                                   [Option(c.name, c, 'text') for c in found], E.card)
            first = o.value
            rest = [c for c in found if c is not first]
            for c in found:
                E.me.limbo.remove(c)
            E.me.deck[0:0] = [first] + rest
        else:
            E.me.deck[0:0] = found
    return step


# --- olhar o topo / revelar
@pattern(r"Look at the top card of your deck")
def _(m):
    def step(E):
        E.data['peek'] = E.me.deck[0] if E.me.deck else None
    return step


@pattern(r"You may discard that card")
def _(m):
    def step(E):
        c = E.data.get('peek')
        if c is not None and c in E.me.deck and (yield from E.g.yes_no(E.p, f'Descartar {c.name}?', source=E.card)):
            E.me.deck.remove(c)
            E.me.discard.append(c)
    return step


@pattern(r"Look at the top card of your opponent's deck")
def _(m):
    def step(E):
        E.data['peek'] = E.op.deck[0] if E.op.deck else None
        if E.data['peek'] is not None:
            E.g.say(f'Topo do baralho do oponente: {E.data["peek"].name}')
    return step


@pattern(r"You may have your opponent shuffle their deck")
def _(m):
    def step(E):
        if E.op.deck and (yield from E.g.yes_no(E.p, 'Fazer o oponente embaralhar o baralho?', source=E.card)):
            E.g.shuffle(E.opp)
    return step


@pattern(r"Look at (\d+) of your opponent's face-down Prize cards")
def _(m):
    def step(E):
        if E.op.prizes:
            c = E.g.rng.choice(E.op.prizes)
            E.g.say(f'Prêmio do oponente: {c.name}')
    return step


@pattern(r"You may turn 1 of your face-down Prize cards face up")
def _(m):
    return None


@pattern(r"Look at the top (\d+) cards of your deck")
def _(m):
    n = int(m.group(1))

    def step(E):
        E.data['looked'] = list(E.me.deck[:n])
    return step


@pattern(r"(?:Look at the top (\d+) cards of your deck, and you |You )may (?:reveal )?(?:any number of|put any number of) Pokémon you find there(?: and put them into your hand| onto your Bench)")
def _(m):
    to_hand = 'hand' in m.group(0)
    reveal_n = m.group(1)

    def step(E):
        if reveal_n:
            E.data['looked'] = list(E.me.deck[:int(reveal_n)])
        cards = [c for c in E.data.get('looked', []) if c.d.kind == 'pokemon' and c in E.me.deck]
        if to_hand:
            got = yield from E.g.choose_cards(E.p, cards, len(cards), 0, 'look', 'Pokémon para a mão', E.card,
                                              key=lambda c: c.d.id)
            for c in got:
                E.me.deck.remove(c)
                E.me.hand.append(c)
        else:
            k = E.g.bench_space(E.p)   # ruling 2045: qualquer Pokémon (Estágio 1/2 também) pode ir ao Banco
            got = yield from E.g.choose_cards(E.p, cards, min(k, len(cards)), 0, 'look', 'Pokémon para o Banco',
                                              E.card, key=lambda c: c.d.id)
            for c in got:
                E.me.deck.remove(c)
                yield from E.g.play_to_bench(E.p, c)
        # ruling 2403: sem carta para devolver ao baralho, não embaralha
        if not reveal_n or any(c in E.me.deck for c in E.data.get('looked', [])):
            E.g.shuffle(E.p)
    return step


# ====================================================================== condições especiais
ALL_CONDS = ['Asleep', 'Burned', 'Confused', 'Paralyzed', 'Poisoned']


@pattern(r"(?:Your opponent's Active Pokémon|The Defending Pokémon|That Pokémon|The new Active Pokémon|It) is now ((?:Asleep|Burned|Confused|Paralyzed|Poisoned)(?:,? (?:and )?(?:Asleep|Burned|Confused|Paralyzed|Poisoned))*)")
def _(m):
    cs = [lib.cond_word(x) for x in re.findall('|'.join(ALL_CONDS), m.group(1))]
    new_active = m.group(0).startswith('The new')

    def step(E):
        t = E.op.active if new_active else E.opp_active()
        for c in cs:
            E.g.add_condition(t, c, E.ctx)
    return step


@pattern(r"Both Active Pokémon are now (Asleep|Burned|Confused|Paralyzed|Poisoned)")
def _(m):
    c = lib.cond_word(m.group(1))

    def step(E):
        E.g.add_condition(E.opp_active(), c, E.ctx)
        E.g.add_condition(E.slot, c)
    return step


@pattern(r"Choose (?:a Special Condition|(Burned, Confused, or Poisoned))")
def _(m):
    opts = ['Burned', 'Confused', 'Poisoned'] if m.group(1) else ALL_CONDS

    def step(E):
        from ..engine import Game
        o = yield from E.g.ask(E.p, 'condition', 'Escolha uma Condição Especial',
                               [Option(Game._cond_pt(lib.cond_word(c)), lib.cond_word(c), 'text') for c in opts], E.card)
        E.data['cond'] = o.value
    return step


@pattern(r"Your opponent's Active Pokémon is now affected by that Special Condition")
def _(m):
    return lambda E: E.g.add_condition(E.opp_active(), E.data['cond'], E.ctx) if E.data.get('cond') else None


@pattern(r"You may discard (\d+) (\w+) Energy from this Pokémon and make your opponent's Active Pokémon (Asleep|Burned|Confused|Paralyzed|Poisoned)")
def _(m):
    n, code, c = int(m.group(1)), NAME_TO_TYPE[m.group(2)], lib.cond_word(m.group(3))

    def step(E):
        pool = [e for e in E.slot.energy if e.d.provides == code]
        if len(pool) < n or not (yield from E.g.yes_no(E.p, f'Descartar {n} Energia(s) para causar {m.group(3)}?',
                                                       source=E.card)):
            return
        got = yield from E.g.choose_cards(E.p, pool, n, n, 'pick', 'Energias a descartar', E.card, key=lambda c: c.uid)
        E.g.discard_energy(E.slot, got, E.ctx)
        E.g.add_condition(E.opp_active(), c, E.ctx)
    return step


@pattern(r"You may have this Pokémon also do (\d+) damage to itself and make your opponent's Active Pokémon (Asleep|Burned|Confused|Paralyzed|Poisoned)")
def _(m):
    n, c = int(m.group(1)), lib.cond_word(m.group(2))

    def step(E):
        if (yield from E.g.yes_no(E.p, f'Causar {n} de dano a este Pokémon para causar {m.group(2)}?', source=E.card)):
            E.g.deal_attack_damage(E.ctx, E.slot, n)
            E.g.add_condition(E.opp_active(), c, E.ctx)
    return step


@pattern(r"(?:During Pokémon Checkup, )?[Pp]ut (\d+) damage counters instead of (\d+) on that Pokémon for this Special Condition")
def _(m):
    n = int(m.group(1))

    def step(E):
        t = E.opp_active()
        if t is not None and 'confused' in t.conditions:
            t.flags['confused_n'] = n
    return step


@pattern(r"During Pokémon Checkup, (?:place|put) (\d+) damage counters on that Pokémon instead of (\d+)")
def _(m):
    n = int(m.group(1))

    def step(E):
        t = E.opp_active()
        if t is not None and 'poisoned' in t.conditions:
            t.flags['poison_n'] = n
    return step


# ====================================================================== troca
@pattern(r"(?:You may )?[Ss]witch (?:this Pokémon|it) with your Active Pokémon")
def _(m):
    def step(E):
        if E.me.active is None or E.slot not in E.me.bench:
            return
        yield from E.g.switch_active(E.p, E.slot)
    return step


@pattern(rf"(?:You may )?[Ss]witch this Pokémon with {NUMW} of your Benched (.*?)Pokémon")
def _(m):
    f = slot_filter(m.group(2) + 'Pokémon')

    def step(E):
        c = [s for s in E.me.bench if f(E.g, s)]
        if not c or not E.g.is_active(E.slot):
            return
        s = yield from E.g.choose_slot(E.p, c, 'switch', 'Escolha o novo Ativo', E.card)
        yield from E.g.switch_active(E.p, s)
    return step


@pattern(r"(?:You may )?[Ss]witch out your opponent's Active Pokémon to the Bench")
def _(m):
    optional = m.group(0).startswith('You may')

    def step(E):
        E.data['did'] = False
        if E.op.active is None or not E.op.bench or (E.ctx is not None and E.g.effects_prevented(E.ctx, E.op.active)):
            return
        if optional and not (yield from E.g.yes_no(E.p, 'Trocar o Ativo do oponente?', source=E.card)):
            return
        yield from lib.opp_switches_out(E.g, E.p, E.card)
        E.data['did'] = True
    return step


@pattern(r"Switch 1 of your opponent's Benched Pokémon with their Active Pokémon")
def _(m):
    def step(E):
        yield from lib.gust(E.g, E.p, source=E.card)
    return step


@pattern(r"Switch in 1 of your opponent's Benched Pokémon that has (\d+) HP or less remaining to the Active Spot")
def _(m):
    n = int(m.group(1))

    def step(E):
        yield from lib.gust(E.g, E.p, lambda g, s: g.hp_left(s) <= n, source=E.card)
    return step


# ====================================================================== mover Energia / contadores
_MOVE_SRC = {
    'this Pokémon': lambda E: [E.slot],
    '1 of your Benched Pokémon': lambda E: list(E.me.bench),
    'your Benched Pokémon': lambda E: list(E.me.bench),
    '1 of your other Pokémon': lambda E: [s for s in E.me.in_play() if s is not E.slot],
    '1 of your Pokémon': lambda E: E.me.in_play(),
    'your Pokémon': lambda E: E.me.in_play(),
    "1 of your opponent's Pokémon": lambda E: E.op.in_play(),
    "your opponent's Active Pokémon": lambda E: [E.op.active] if E.op.active else [],
    "your opponent's Pokémon": lambda E: E.op.in_play(),
    "your opponent's Benched Pokémon": lambda E: list(E.op.bench),
}
_MOVE_DST = {
    'your Active Pokémon': lambda E: [E.me.active] if E.me.active else [],
    'this Pokémon': lambda E: [E.slot],
    '1 of your Benched Pokémon': lambda E: list(E.me.bench),
    'another of your Pokémon': lambda E: E.me.in_play(),
    'your other Pokémon': lambda E: E.me.in_play(),
    '1 of their Benched Pokémon': lambda E: list(E.op.bench),
    'another of their Pokémon': lambda E: E.op.in_play(),
    'their other Pokémon': lambda E: E.op.in_play(),
    'their Active Pokémon': lambda E: [E.op.active] if E.op.active else [],
}


@pattern(r"(You may )?[Mm]ove (an|a|\d+|any amount of|any number of|all) ?(Basic )?(?:({0}) )?Energy(?: cards?)? from (.+?) to (.+?)(?: in any way you like)?".format(TYPE_WORDS))
def _(m):
    optional = bool(m.group(1))
    q = m.group(2)
    n = 99 if q in ('any amount of', 'any number of', 'all') else num(q)
    basic = bool(m.group(3))
    code = NAME_TO_TYPE.get(m.group(4)) if m.group(4) else None
    src, dst = m.group(5), m.group(6)
    if src not in _MOVE_SRC or dst not in _MOVE_DST:
        raise Unparsed(f'mover: {src} → {dst}')

    def step(E):
        def pred(e):
            if basic and not e.d.basic_energy:
                return False
            if code is None or e.d.provides == code:
                return True
            if e.d.special_energy and e.d.impl is not None and e.d.impl.units is not None:
                # ruling 2312: Energia Especial que fornece o tipo (ex.: Legacy Energy) também pode ser movida
                s = next((s for s in E.me.in_play() if e in s.energy), None)
                return s is not None and any(code in u for u in e.d.impl.units(E.g, e, s))
            return False
        def srcs():  # ruling 2375: Mist Energy etc. impedem tirar Energia do Pokémon do oponente
            return [s for s in _MOVE_SRC[src](E) if not (s.owner != E.p and E.g.effects_prevented(E.ctx, s))]
        yield from lib.move_energy(E.g, E.p, srcs, lambda: _MOVE_DST[dst](E), n, pred, E.card,
                                   min_n=0 if (optional or n >= 99) else n)
    return step


@pattern(r"Move all damage counters from 1 of your Benched (.*?)Pokémon to (your opponent's Active Pokémon|1 of your opponent's Pokémon)")
def _(m):
    f = slot_filter(m.group(1) + 'Pokémon')
    to_active = 'Active' in m.group(2)

    def step(E):
        src_c = [s for s in E.me.bench if s.damage > 0 and f(E.g, s)]
        if not src_c or not E.g.allowed('damage_counters_movable'):
            return
        src = yield from E.g.choose_slot(E.p, src_c, 'move_from', 'Mover contadores de qual Pokémon?', E.card)
        dst = E.opp_active() if to_active else (yield from E.g.choose_slot(E.p, E.op.in_play(), 'counters',
                                                                         'Para qual Pokémon do oponente?', E.card))
        if dst is None or E.g.anyhook('prevent_counters', target=dst, kind='attack', by=E.p):
            return
        k = src.damage // 10
        src.damage = 0
        E.g.place_counters(dst, k, E.kind, by=E.p, ctx=E.ctx)
    return step


@pattern(r"Move 1 damage counter from 1 of your (.*?)Pokémon to another of your Pokémon")
def _(m):
    f = slot_filter(m.group(1) + 'Pokémon')

    def step(E):
        src_c = [s for s in E.me.in_play() if s.damage > 0 and f(E.g, s)]
        if not src_c:
            return
        src = yield from E.g.choose_slot(E.p, src_c, 'move_from', 'Mover 1 contador de qual Pokémon?', E.card)
        dst_c = [s for s in E.me.in_play() if s is not src]
        if not dst_c:
            return
        dst = yield from E.g.choose_slot(E.p, dst_c, 'counters', 'Para qual Pokémon?', E.card)
        src.damage -= 10
        dst.damage += 10
    return step


@pattern(r"You may move any number of damage counters from your opponent's (Benched )?Pokémon to their (Active|other) Pokémon(?: in any way you like)?")
def _(m):
    bench_src = bool(m.group(1))
    to_active = m.group(2) == 'Active'

    def step(E):
        if not E.g.allowed('damage_counters_movable'):
            return
        budget = sum(s.damage // 10 for s in E.op.in_play())
        while budget > 0:
            budget -= 1
            src_c = [s for s in (E.op.bench if bench_src else E.op.in_play()) if s.damage > 0]
            if not src_c:
                return
            o = yield from E.g.ask(E.p, 'move_more', 'Mover um contador de dano?',
                                   [Option('Sim', True, 'text'), Option('Não, terminar', False, 'text')], E.card)
            if not o.value:
                return
            src = yield from E.g.choose_slot(E.p, src_c, 'move_from', 'Mover 1 contador de qual Pokémon?', E.card)
            dst_c = [E.op.active] if to_active else [s for s in E.op.in_play() if s is not src]
            dst_c = [s for s in dst_c if s is not None and s is not src]
            if not dst_c:
                return
            dst = yield from E.g.choose_slot(E.p, dst_c, 'counters', 'Para qual Pokémon?', E.card)
            src.damage -= 10
            dst.damage += 10
    return step


@pattern(rf"Choose {NUMW} of your opponent's Pokémon and (?:put|place) (\d+) damage counters on each of them")
def _(m):
    k, n = num(m.group(1)), int(m.group(2))

    def step(E):
        chosen = []
        for _ in range(k):
            c = [s for s in E.op.in_play() if s not in chosen]
            if not c:
                break
            chosen.append((yield from E.g.choose_slot(E.p, c, 'counters', f'Colocar {n} contadores em', E.card)))
        for s in chosen:
            E.g.place_counters(s, n, E.kind, by=E.p, ctx=E.ctx)
    return step


@pattern(rf"Choose {NUMW} of your opponent's Pokémon and quadruple the number of damage counters on each of them")
def _(m):
    k = num(m.group(1))

    def step(E):
        chosen = []
        for _ in range(k):
            c = [s for s in E.op.in_play() if s not in chosen]
            if not c:
                break
            chosen.append((yield from E.g.choose_slot(E.p, c, 'counters', 'Quadruplicar contadores de', E.card)))
        for s in chosen:
            E.g.place_counters(s, 3 * (s.damage // 10), E.kind, by=E.p, ctx=E.ctx)
    return step


@pattern(r"Double the number of damage counters on each of your opponent's Pokémon")
def _(m):
    def step(E):
        for s in list(E.op.in_play()):
            E.g.place_counters(s, s.damage // 10, E.kind, by=E.p, ctx=E.ctx)
    return step


@pattern(r"(?:Put|Place) damage counters on each of your opponent's Benched Pokémon until its remaining HP is (\d+)")
def _(m):
    n = int(m.group(1))

    def step(E):
        for s in list(E.op.bench):
            left = E.g.hp_left(s)
            if left > n:
                E.g.place_counters(s, (left - n) // 10, E.kind, by=E.p, ctx=E.ctx)
    return step


@pattern(r"(?:Put|Place) (\d+) damage counters on each of your opponent's Pokémon that has any damage counters on it")
def _(m):
    n = int(m.group(1))

    def step(E):
        for s in list(E.op.in_play()):
            if s.damage > 0:
                E.g.place_counters(s, n, E.kind, by=E.p, ctx=E.ctx)
    return step


@pattern(r"(?:Put|Place) (\d+) damage counters on each Pokémon that has an Ability")
def _(m):
    n = int(m.group(1))

    def step(E):
        for s in list(E.me.in_play() + E.op.in_play()):
            if E.g.has_ability(s):
                E.g.place_counters(s, n, E.kind, by=E.p, ctx=E.ctx)
    return step


@pattern(r"(?:Put|Place) (\d+) damage counters on this Pokémon")
def _(m):
    n = int(m.group(1))

    def step(E):
        E.data['did'] = E.g.place_counters(E.slot, n, 'other', by=E.p) > 0
    return step


@pattern(r"Put up to (\d+) damage counters on this Pokémon", 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        k = n   # ruling 1984: pode colocar todos, mesmo nocauteando o próprio Pokémon
        o = yield from E.g.ask(E.p, 'amount', 'Quantos contadores colocar?',
                               [Option(f'{i}', i, 'text') for i in range(k, -1, -1)], E.card)
        E.g.place_counters(E.slot, o.value, 'other', by=E.p)
        E.data['placed'] = o.value
    return step


@pattern(r"This attack does (\d+) damage for each damage counter you placed in this way", 'pre')
def _(m):
    n = int(m.group(1))
    return _dmg_set(lambda E: n * E.data.get('placed', 0))


@pattern(r"During this turn, attacks used by this Pokémon do (\d+) more damage to your opponent's Active Pokémon")
def _(m):
    n = int(m.group(1))

    def step(E):
        s = E.slot
        E.g.add_effect(f'ataques +{n}', E.p, {'damage_out': lambda g, src, dmg, ctx, target, s=s:
                       dmg + n if ctx.attacker is s else None}, target=s, duration='this_turn')
    return step


# ====================================================================== efeitos com duração
def _guard_effect(E, t):
    return t is None or (E.ctx is not None and E.g.effects_prevented(E.ctx, t))


@pattern(r"Choose 1 of your opponent's Active Pokémon's attacks")
def _(m):
    def step(E):
        t = E.opp_active()
        E.data['locked'] = None
        if t is None:
            return
        a = yield from choose_attack(E, [(t, x) for x in E.g.attacks_of(t)], 'Qual ataque bloquear?', copy=False)
        E.data['locked'] = a.name if a is not None else None
    return step


@pattern(r"During your opponent's next turn, that Pokémon can't use that attack")
def _(m):
    def step(E):
        t, name = E.opp_active(), E.data.get('locked')
        if _guard_effect(E, t) or not name:
            return
        E.g.add_effect(f'não pode usar {name}', E.p,
                       {'can_attack': lambda g, src, slot, attack, t=t, name=name:
                        False if slot is t and attack.name == name else None},
                       target=t, duration='opp_next_turn', while_active=True)
    return step


def _weakness_change(t_word, n_turns):
    code = NAME_TO_TYPE[t_word]

    def step(E):
        t = E.opp_active()
        if _guard_effect(E, t):
            return
        E.g.add_effect(f'Fraqueza {t_word}', E.p, {'weakness': lambda g, src, v, slot, t=t:
                                                    (code, 2) if slot is t else None},
                       target=t, duration='my_next_turn')
    return step


@pattern(rf"(?:Until the end of your next turn, )?[Tt]he Defending Pokémon's Weakness is now ({TYPE_WORDS})(?: until the end of your next turn)?")
def _(m):
    return _weakness_change(m.group(1), 2)


@pattern(r"During your opponent's next turn, this Pokémon has no Weakness")
def _(m):
    def step(E):
        s = E.slot
        E.g.add_effect('sem Fraqueza', E.p, {'weakness': lambda g, src, v, slot, s=s: (None, 1) if slot is s else None},
                       target=s, duration='opp_next_turn')
    return step


def _attacker_pred(desc):
    d = desc.strip()
    if d == 'Pokémon that have an Ability':
        return lambda g, a: g.has_ability(a)
    if d == 'Ancient Pokémon':
        return lambda g, a: 'ancient' in a.d.tags
    if d == 'Burned Pokémon':
        return lambda g, a: 'burned' in a.conditions
    if d == 'Evolution Pokémon':
        return lambda g, a: a.d.stage > 0
    if d == 'Pokémon ex':
        return lambda g, a: a.d.is_ex
    raise Unparsed(d)


@pattern(r"During your opponent's next turn, prevent all damage done to this Pokémon by attacks from (Pokémon that have an Ability|Ancient Pokémon|Burned Pokémon)")
def _(m):
    f = _attacker_pred(m.group(1))

    def step(E):
        s = E.slot
        E.g.add_effect('proteção', E.p, {'damage_in': lambda g, src, dmg, ctx, target, active, s=s:
                       0 if target is s and ctx.player != s.owner and f(g, ctx.attacker) else None},
                       target=s, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"During your opponent's next turn, this Pokémon takes (\d+) (more|less) damage from attacks(?: from (Evolution) Pokémon)?")
def _(m):
    n = int(m.group(1)) * (1 if m.group(2) == 'more' else -1)
    evo = bool(m.group(3))

    def step(E):
        s = E.slot
        E.g.add_effect('dano recebido', E.p, {'damage_in': lambda g, src, dmg, ctx, target, active, s=s:
                       dmg + n if target is s and ctx.player != s.owner and dmg > 0 and
                       (not evo or ctx.attacker.d.stage > 0) else None},
                       target=s, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"During your opponent's next turn, prevent all damage done to each of your Future Pokémon by attacks from Pokémon ex")
def _(m):
    def step(E):
        p = E.p
        E.g.add_effect('C.O.D.E.: Protect', p, {'damage_in': lambda g, src, dmg, ctx, target, active:
                       0 if target.owner == p and 'future' in target.d.tags and ctx.player != p and ctx.attacker.d.is_ex
                       else None}, target=E.slot, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"If this Pokémon is no longer your Active Pokémon, this effect ends")
def _(m):
    return None


@pattern(r"During your opponent's next turn, if this Pokémon is damaged by an attack, (?:put|place) (\d+) damage counters on the Attacking Pokémon")
def _(m):
    n = int(m.group(1))

    def step(E):
        s = E.slot

        def ev(g, src, ctx, slot, damage, s=s):
            if slot is s and ctx.player != s.owner and g.in_play(ctx.attacker) \
                    and not g.effects_prevented_from(s.owner, s, ctx.attacker):
                g.place_counters(ctx.attacker, n, 'other', by=s.owner)
        E.g.add_effect('contra-ataque', E.p, events={'damaged_by_attack': ev}, target=s, duration='opp_next_turn',
                       while_active=True)
    return step


@pattern(r"During your opponent's next turn, if this Pokémon is damaged by an attack, put damage counters on the Attacking Pokémon equal to the damage done to this Pokémon")
def _(m):
    def step(E):
        s = E.slot

        def ev(g, src, ctx, slot, damage, s=s):
            if slot is s and ctx.player != s.owner and g.in_play(ctx.attacker) \
                    and not g.effects_prevented_from(s.owner, s, ctx.attacker):
                g.place_counters(ctx.attacker, damage // 10, 'other', by=s.owner)
        E.g.add_effect('contra-ataque', E.p, events={'damaged_by_attack': ev}, target=s, duration='opp_next_turn',
                       while_active=True)
    return step


@pattern(r"During your opponent's next turn, whenever they attach an Energy card from their hand to the Defending Pokémon, place (\d+) damage counters on that Pokémon")
def _(m):
    n = int(m.group(1))

    def step(E):
        t = E.opp_active()
        if _guard_effect(E, t):
            return

        def ev(g, src, player, card, slot, from_hand, t=t):
            if slot is t and from_hand:
                g.place_counters(t, n, 'other', by=src.owner)
        E.g.add_effect('Energia dói', E.p, events={'energy_attached': ev}, target=t, duration='opp_next_turn',
                       while_active=True)
    return step


@pattern(r"During your opponent's next turn, if they attach an Energy card from their hand to the Defending Pokémon, their turn ends")
def _(m):
    def step(E):
        t = E.opp_active()
        if _guard_effect(E, t):
            return

        def ev(g, src, player, card, slot, from_hand, t=t):
            if slot is t and from_hand:
                g.turn_ended = True
        E.g.add_effect('sono profundo', E.p, events={'energy_attached': ev}, target=t, duration='opp_next_turn',
                       while_active=True)
    return step


@pattern(r"During your opponent's next turn, Energy(?: cards)? can't be attached from your opponent's hand to (?:the Defending Pokémon|that Pokémon)")
def _(m):
    def step(E):
        t = E.opp_active()
        if _guard_effect(E, t):
            return
        E.g.add_effect('sem Energia', E.p, {'can_attach': lambda g, src, player, card, slot, t=t:
                                            False if slot is t and card in g.players[player].hand else None},
                       target=t, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"During your opponent's next turn, attacks used by the Defending Pokémon cost (Colorless)+ more, and its Retreat Cost is (Colorless)+ more")
def _(m):
    def step(E):
        t = E.opp_active()
        if _guard_effect(E, t):
            return
        E.g.add_effect('custos maiores', E.p,
                       {'attack_cost': lambda g, src, cost, slot, attack, t=t: cost + ['C'] if slot is t else None,
                        'retreat_cost': lambda g, src, v, slot, t=t: v + 1 if slot is t else None},
                       target=t, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"During your opponent's next turn, Pokémon that have (\d+) or less Energy attached can't attack")
def _(m):
    n = int(m.group(1))

    def step(E):
        p = E.p
        E.g.add_effect('Energia mínima', p, {'can_attack': lambda g, src, slot, attack:
                                             False if slot.owner != p and g.energy_count(slot) <= n else None},
                       duration='opp_next_turn')
    return step


@pattern(r"During your next turn, your Pokémon can't attack")
def _(m):
    def step(E):
        p = E.p
        E.g.add_effect('não podem atacar', p, {'can_attack': lambda g, src, slot, attack:
                                               False if slot.owner == p else None}, duration='my_next_turn')
    return step


@pattern(r"(?:It|The Defending Pokémon) can't attack during your opponent's next turn")
def _(m):
    def step(E):
        t = E.opp_active()
        if _guard_effect(E, t):
            return
        E.g.add_effect('não pode atacar', E.p, {'can_attack': lambda g, src, slot, attack, t=t:
                                                False if slot is t else None},
                       target=t, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"During your opponent's next turn, they can't play any (Supporter|Item|Stadium) cards? from their hand")
def _(m):
    kind = m.group(1).lower()

    def step(E):
        o = E.opp
        E.g.add_effect(f'trava de {m.group(1)}', E.p, {'can_play': lambda g, src, player, card, o=o:
                                                       False if player == o and card.d.subtype == kind else None},
                       duration='opp_next_turn')
    return step


@pattern(r"Your opponent can't play any (Supporter|Item|Stadium) cards from their hand during their next turn")
def _(m):
    kind = m.group(1).lower()

    def step(E):
        o = E.opp
        E.g.add_effect(f'trava de {m.group(1)}', E.p, {'can_play': lambda g, src, player, card, o=o:
                                                       False if player == o and card.d.subtype == kind else None},
                       duration='opp_next_turn')
    return step


@pattern(r"During your opponent's next turn, they can't play any Pokémon from their hand to evolve their Pokémon")
def _(m):
    def step(E):
        o = E.opp
        E.g.add_effect('sem evoluir', E.p, {'can_evolve': lambda g, src, player, slot, card, o=o:
                                            False if player == o else None}, duration='opp_next_turn')
    return step


@pattern(r"During your opponent's next turn, if the Defending Pokémon tries to use an attack, your opponent flips 2 coins")
def _(m):
    def step(E):
        t = E.opp_active()
        if _guard_effect(E, t):
            return
        E.g.add_effect('ataque incerto', E.p, target=t, duration='opp_next_turn', while_active=True,
                       smokescreen=True, flips=2)
    return step


@pattern(r"If either of them is tails, that attack doesn't happen")
def _(m):
    return None


@pattern(r"If your opponent's Pokémon is Knocked Out by damage from this attack, during your opponent's next turn, prevent all damage from and effects of attacks done to this Pokémon")
def _(m):
    def step(E):
        if not predicted_ko(E):
            return
        s = E.slot
        E.g.add_effect('proteção', E.p, {'damage_in': lambda g, src, dmg, ctx, target, active, s=s:
                                         0 if target is s and ctx.player != s.owner else None,
                                         'prevent_attack_effects': lambda g, src, ctx, target, s=s: target is s},
                       target=s, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"If your opponent's Pokémon is Knocked Out by damage from this attack, take (\d+) more Prize cards?")
def _(m):
    n = int(m.group(1))

    def step(E):
        t = E.ctx.defender
        if not predicted_ko(E):
            return
        owner = E.p
        E.g.add_effect('prêmio extra', owner, {'prizes': lambda g, src, v, slot, taker, by_attack, attacker, t=t:
                                               v + n if slot is t and taker == owner else None},
                       duration='this_turn')
    return step


@pattern(r"At the end of your opponent's next turn, discard the Defending Pokémon and all attached cards")
def _(m):
    def step(E):
        t = E.opp_active()
        if _guard_effect(E, t):
            return

        def ev(g, src, player, t=t):
            if player != src.owner and g.in_play(t):
                g.remove_slot(t, to='discard')
                yield from g._promote_if_needed()
        E.g.add_effect('descarte retardado', E.p, events={'turn_end': ev}, target=t, duration='opp_next_turn',
                       while_active=True)  # ruling 2404: acaba se o alvo sai do Ativo
    return step


@pattern(r"At the end of your opponent's next turn, put (\d+) damage counters on the Defending Pokémon")
def _(m):
    n = int(m.group(1))

    def step(E):
        t = E.opp_active()
        if _guard_effect(E, t):
            return

        def ev(g, src, player, t=t):
            if player != src.owner and g.in_play(t):
                g.place_counters(t, n, 'other', by=src.owner)
        E.g.add_effect('contadores retardados', E.p, events={'turn_end': ev}, target=t, duration='opp_next_turn')
    return step


@pattern(r"At the end of your opponent's next turn, the Defending Pokémon will be Knocked Out")
def _(m):
    def step(E):
        t = E.opp_active()
        if _guard_effect(E, t):
            return

        def ev(g, src, player, t=t):
            if player != src.owner and g.in_play(t):
                t.damage = max(t.damage, g.hp(t))
        E.g.add_effect('nocaute retardado', E.p, events={'turn_end': ev}, target=t, duration='opp_next_turn',
                       while_active=True)   # ruling 1981: recuar ou evoluir cancela
    return step


@pattern(r"During your next turn, if the Defending Pokémon is Knocked Out, take (\d+) more Prize cards")
def _(m):
    n = int(m.group(1))

    def step(E):
        t = E.opp_active()
        owner = E.p
        if t is None:
            return
        n0 = len(t.cards)   # ruling 1957: se o Defensor evoluir, o bônus se perde
        E.g.add_effect('prêmio extra', owner, {'prizes': lambda g, src, v, slot, taker, by_attack, attacker, t=t:
                                               v + n if slot is t and len(t.cards) == n0 and taker == owner else None},
                       duration='my_next_turn')
    return step


# ====================================================================== cura
@pattern(r"Heal (\d+) damage from it")
def _(m):
    n = int(m.group(1))
    return lambda E: E.g.heal(E.slot, n)


@pattern(r"Heal (\d+) damage from each Pokémon")
def _(m):
    n = int(m.group(1))
    return lambda E: [E.g.heal(s, n) for s in E.me.in_play() + E.op.in_play()]


@pattern(r"Heal all damage from (?:each of )?your (Active )?(.*?)Pokémon")
def _(m):
    active = bool(m.group(1))
    f = slot_filter(m.group(2) + 'Pokémon')

    def step(E):
        E.data['healed_slots'] = []
        for s in (([E.me.active] if E.me.active else []) if active else E.me.in_play()):
            if f(E.g, s) and E.g.heal(s, 9999) > 0:
                E.data['healed_slots'].append(s)
    return step


@pattern(r"If you healed any damage in this way, discard all Energy from (?:those|that) Pokémon")
def _(m):
    def step(E):
        for s in E.data.get('healed_slots', []):
            if E.g.in_play(s):
                E.g.discard_energy(s, list(s.energy))
    return step


@pattern(r"Heal (\d+) damage from your Active Pokémon and have it recover from a Special Condition")
def _(m):
    n = int(m.group(1))

    def step(E):
        a = E.me.active
        if a is None:
            return
        E.g.heal(a, n)
        if a.conditions:
            conds = sorted(a.conditions)
            o = yield from E.g.ask(E.p, 'condition', 'Recuperar de qual Condição Especial?',
                                   [Option(c, c, 'text') for c in conds], E.card)
            a.conditions.discard(o.value)
            if o.value == 'paralyzed':
                a.paralyzed_until = -1
    return step


# ====================================================================== mão
@pattern(rf"(?:Have )?[Ee]ach player draws? {NUMW} cards?")
def _(m):
    n = num(m.group(1))
    return lambda E: (E.g.draw(E.p, n), E.g.draw(E.opp, n))


@pattern(rf"Your opponent shuffles their hand into their deck and draws {NUMW} cards|Have your opponent shuffle their hand into their deck and draw {NUMW} cards")
def _(m):
    n = num(m.group(1) or m.group(2))

    def step(E):
        E.g.hand_to_deck(E.opp)
        E.g.draw(E.opp, n)
    return step


@pattern(r"Your opponent shuffles their hand and puts it on the bottom of their deck")
def _(m):
    def step(E):
        E.data['bottomed'] = E.g.hand_to_deck(E.opp, bottom=True)
    return step


@pattern(rf"If they put any cards on the bottom of their deck in this way, they draw {NUMW} cards")
def _(m):
    n = num(m.group(1))
    return lambda E: E.g.draw(E.opp, n) if E.data.get('bottomed') else None


@pattern(rf"Your opponent chooses {NUMW} cards from their hand and shuffles those cards into their deck")
def _(m):
    n = num(m.group(1))

    def step(E):
        k = min(n, len(E.op.hand))
        got = yield from E.g.choose_cards(E.opp, E.op.hand, k, k, 'pick', 'Cartas da mão para o baralho', E.card,
                                          key=lambda c: c.uid)
        for c in got:
            E.op.hand.remove(c)
            E.op.deck.append(c)
        E.g.shuffle(E.opp)
    return step


@pattern(r"(?:Then, )?[Dd]raw a card for each card in your opponent's hand")
def _(m):
    return lambda E: E.g.draw(E.p, len(E.op.hand))


@pattern(r"Discard random cards from your opponent's hand until they have (\d+) cards in their hand")
def _(m):
    n = int(m.group(1))
    return lambda E: lib.opp_discards_random(E.g, E.p, max(0, len(E.op.hand) - n))


@pattern(r"(?:You may )?[Dd]raw (\d+) cards")
def _(m):
    n = int(m.group(1))
    optional = m.group(0).startswith('You may')

    def step(E):
        if optional and not (yield from E.g.yes_no(E.p, f'Comprar {n} cartas?', source=E.card)):
            return
        E.g.draw(E.p, n)
    return step


@pattern(r"Switch a card from your hand with the top card of your deck")
def _(m):
    def step(E):
        if not E.me.hand or not E.me.deck:
            return
        got = yield from E.g.choose_cards(E.p, E.me.hand, 1, 1, 'pick', 'Carta da mão para trocar com o topo', E.card,
                                          key=lambda c: c.uid)
        top = E.me.deck.pop(0)
        E.me.hand.remove(got[0])
        E.me.hand.append(top)
        E.me.deck.insert(0, got[0])
    return step


@pattern(r"Choose a random card from your opponent's hand")
def _(m):
    def step(E):
        E.data['rand_n'] = 1
    return step


@pattern(r"For each heads, choose a random card from your opponent's hand")
def _(m):
    def step(E):
        E.data['rand_n'] = E.data.get('heads_n', 0)
    return step


@pattern(r"Your opponent reveals (?:that card|those cards) and shuffles (?:it|them) into their deck")
def _(m):
    def step(E):
        n = min(E.data.get('rand_n', 0), len(E.op.hand))
        cards = E.g.rng.sample(E.op.hand, n) if n else []
        for c in cards:
            E.op.hand.remove(c)
            E.op.deck.append(c)
        if cards:
            E.g.say(f'{E.op.name} revelou {", ".join(c.name for c in cards)} e embaralhou no baralho')
            E.g.shuffle(E.opp)
    return step


# --- mão revelada
def _revealed_hand(E):
    lib.reveal_hand(E.g, E.opp)
    E.data['revealed'] = list(E.op.hand)
    return E.data['revealed']


@pattern(r"(?:Your opponent reveals their hand, and you|Your opponent reveals their hand\. You) put an? (.+?) you find there on the bottom of your opponent's deck")
def _(m):
    f = card_filter(m.group(1))

    def step(E):
        cards = [c for c in _revealed_hand(E) if f(c)]
        got = yield from E.g.choose_cards(E.p, cards, 1, 0, 'pick', 'Carta para o fundo do baralho dele', E.card,
                                          key=lambda c: c.d.id)
        for c in got:
            E.op.hand.remove(c)
            E.op.deck.append(c)
    return step


@pattern(r"Your opponent reveals their hand, and you choose a card you find there and put it on the bottom of their deck")
def _(m):
    def step(E):
        cards = _revealed_hand(E)
        got = yield from E.g.choose_cards(E.p, cards, 1, 1 if cards else 0, 'pick', 'Carta para o fundo do baralho dele',
                                          E.card, key=lambda c: c.d.id)
        for c in got:
            E.op.hand.remove(c)
            E.op.deck.append(c)
    return step


@pattern(r"Your opponent reveals their hand, and you discard a card you find there")
def _(m):
    def step(E):
        cards = _revealed_hand(E)
        got = yield from E.g.choose_cards(E.p, cards, 1, 1 if cards else 0, 'pick', 'Carta para descartar', E.card,
                                          key=lambda c: c.d.id)
        for c in got:
            E.op.hand.remove(c)
            E.op.discard.append(c)
    return step


@pattern(r"Discard a card you find there")
def _(m):
    def step(E):
        cards = [c for c in E.data.get('revealed', []) if c in E.op.hand]
        got = yield from E.g.choose_cards(E.p, cards, 1, 1 if cards else 0, 'pick', 'Carta para descartar', E.card,
                                          key=lambda c: c.d.id)
        for c in got:
            E.op.hand.remove(c)
            E.op.discard.append(c)
    return step


@pattern(r"Discard all (.+?) you find there")
def _(m):
    f = or_filter(m.group(1).replace(' and ', ' or '))

    def step(E):
        for c in list(E.data.get('revealed', [])):
            if c in E.op.hand and f(c):
                E.op.hand.remove(c)
                E.op.discard.append(c)
    return step


def _bench_basics_from_hand(E, f, k, hp_max=None):
    cards = [c for c in E.op.hand if c.d.is_basic and f(c) and (hp_max is None or c.d.hp <= hp_max)]
    got = yield from E.g.choose_cards(E.p, cards, min(k, E.g.bench_space(E.opp)), 0, 'pick',
                                      'Pokémon para o Banco do oponente', E.card, key=lambda c: c.d.id)
    for c in got:
        E.op.hand.remove(c)
        yield from E.g.play_to_bench(E.opp, c)
    return got


@pattern(r"Your opponent reveals their hand, and you put a Basic Pokémon with (\d+) HP or less that you find there onto your opponent's Bench")
def _(m):
    hp = int(m.group(1))

    def step(E):
        _revealed_hand(E)
        yield from _bench_basics_from_hand(E, lambda c: True, 1, hp)
    return step


@pattern(r"Have your opponent reveal their hand and you put any number of Basic Pokémon you find there onto their Bench")
def _(m):
    def step(E):
        _revealed_hand(E)
        yield from _bench_basics_from_hand(E, lambda c: True, 99)
    return step


@pattern(r"Put up to (\d+) Basic Pokémon you find there onto your opponent's Bench")
def _(m):
    n = int(m.group(1))

    def step(E):
        yield from _bench_basics_from_hand(E, lambda c: True, n)
    return step


@pattern(r"You may use the effect of a Supporter card you find there as the effect of this attack")
def _(m):
    def step(E):
        cards = [c for c in E.data.get('revealed', []) if c in E.op.hand and c.d.is_supporter and
                 c.d.impl is not None and c.d.impl.run is not None]
        if not cards:
            return
        got = yield from E.g.choose_cards(E.p, cards, 1, 0, 'pick', 'Usar o efeito de qual Apoiador?', E.card,
                                          key=lambda c: c.d.id)
        for c in got:
            yield from run(c.d.impl.run(E.g, E.p, c))
    return step


@pattern(r"For each heads, choose a card you find there and shuffle it into your opponent's deck")
def _(m):
    def step(E):
        for _ in range(E.data.get('heads_n', 0)):
            cards = [c for c in E.data.get('revealed', []) if c in E.op.hand]
            got = yield from E.g.choose_cards(E.p, cards, 1, 1 if cards else 0, 'pick', 'Carta para o baralho dele',
                                              E.card, key=lambda c: c.d.id)
            for c in got:
                E.op.hand.remove(c)
                E.op.deck.append(c)
        E.g.shuffle(E.opp)
    return step


@pattern(r"Reveal any number of (.+?) from your hand, and this attack does (\d+) damage for each card you revealed in this way", 'pre')
def _(m):
    names = [x.strip() for x in re.split(r',\s*(?:and\s+)?|\s+and\s+', m.group(1)) if x.strip()]
    n = int(m.group(2))

    def step(E):
        cands = [c for c in E.me.hand if c.name in names]
        got = yield from E.g.choose_cards(E.p, cands, len(cands), 0, 'pick', 'Cartas para revelar', E.card,
                                          key=lambda c: c.uid)
        E.ctx.damage = n * len(got)
    step.est = lambda E, d: n * sum(1 for c in E.me.hand if c.name in names)
    return step


@pattern(r"Reveal the top (\d+) cards of your deck")
def _(m):
    n = int(m.group(1))

    def step(E):
        E.data['revealed'] = list(E.me.deck[:n])
        E.g.say(f'Reveladas: {", ".join(c.name for c in E.data["revealed"])}')
    return step


@pattern(r"Reveal the bottom (\d+) cards of your deck")
def _(m):
    n = int(m.group(1))

    def step(E):
        E.data['revealed'] = list(E.me.deck[-n:])
        E.g.say(f'Reveladas: {", ".join(c.name for c in E.data["revealed"])}')
    return step


@pattern(r"Then, discard those (.+?) cards and shuffle the other cards back into your deck")
def _(m):
    f = card_filter(m.group(1) + ' card')

    def step(E):
        for c in E.data.get('revealed', []):
            if c in E.me.deck and f(c):
                E.me.deck.remove(c)
                E.me.discard.append(c)
        E.g.shuffle(E.p)
    return step


@pattern(r"Then, shuffle any revealed Pokémon back into your deck")
def _(m):
    def step(E):
        for c in E.data.get('revealed', []):
            if c in E.me.deck and c.d.kind == 'pokemon':
                E.me.deck.remove(c)
                E.me.deck.append(c)
        E.data['revealed_left'] = [c for c in E.data.get('revealed', []) if c in E.me.deck and c.d.kind != 'pokemon']
        E.g.shuffle(E.p)
    return step


@pattern(r"Discard the other cards")
def _(m):
    def step(E):
        for c in E.data.get('revealed_left', []):
            if c in E.me.deck:
                E.me.deck.remove(c)
                E.me.discard.append(c)
    return step


# ====================================================================== evoluir do baralho
def _evo_cards(E, slot):
    return [x for x in E.me.deck if x.d.is_evolution and slot.name in E.g.fold('evolves_from', {x.d.evolves_from}, slot=slot, card=x)]


def evolve_from_deck(E, slots, shuffle=True):
    for s in slots:
        if not E.g.in_play(s):
            continue
        c = _evo_cards(E, s)
        if not c:
            continue
        got = yield from E.g.choose_cards(E.p, c, 1, 0, 'search', f'Evoluir {s.name} com', E.card)
        for x in got:
            E.me.deck.remove(x)
            yield from E.g.evolve(E.p, s, x, from_hand=False)
    if shuffle:
        E.g.shuffle(E.p)


@pattern(r"Search your deck for a card that evolves from 1 of your Pokémon and put it onto that Pokémon to evolve it")
def _(m):
    def step(E):
        pool = [s for s in E.me.in_play() if _evo_cards(E, s)]
        cards = {x for s in pool for x in _evo_cards(E, s)}
        got = yield from E.g.choose_cards(E.p, list(cards), 1, 0, 'search', 'Evoluir com', E.card)
        for x in got:
            targets = [s for s in pool if x in _evo_cards(E, s)]
            s = yield from E.g.choose_slot(E.p, targets, 'evolve_target', f'Evoluir qual Pokémon com {x.name}?', E.card)
            E.me.deck.remove(x)
            yield from E.g.evolve(E.p, s, x, from_hand=False)
        E.g.shuffle(E.p)
    return step


@pattern(r"For each of your Benched Pokémon, search your deck for a card that evolves from that Pokémon and put it onto that Pokémon to evolve it")
def _(m):
    return lambda E: evolve_from_deck(E, list(E.me.bench))


@pattern(r"Choose up to (\d+) of your (.*?)Pokémon")
def _(m):
    k = int(m.group(1))
    f = slot_filter(m.group(2) + 'Pokémon')

    def step(E):
        chosen = []
        for _ in range(k):
            c = [s for s in E.me.in_play() if f(E.g, s) and s not in chosen]
            s = yield from E.g.choose_slot(E.p, c, 'evolve_target', 'Escolha um Pokémon', E.card, optional=True)
            if s is None:
                break
            chosen.append(s)
        E.data['chosen_own'] = chosen
    return step


@pattern(r"For each of those Pokémon, search your deck for a card that evolves from that Pokémon and put it onto that Pokémon to evolve it")
def _(m):
    return lambda E: evolve_from_deck(E, list(E.data.get('chosen_own', [])))


@pattern(r"Search your deck for an? (.+?) or (?:an? )?(.+?) and put it onto this (\w[\w\-]*) to evolve it")
def _(m):
    names = {m.group(1), m.group(2)}

    def step(E):
        c = [x for x in E.me.deck if x.name in names]   # ruling 1949: pula o Estágio 1
        got = yield from E.g.choose_cards(E.p, c, 1, 0, 'search', 'Evoluir com', E.card)
        for x in got:
            E.me.deck.remove(x)
            yield from E.g.evolve(E.p, E.slot, x, from_hand=False)
        E.g.shuffle(E.p)
    return step


# ====================================================================== desevoluir
def _devolve(E, slots, to):
    for s in slots:
        if not s.evolved or not E.g.in_play(s) or (E.ctx is not None and E.g.effects_prevented(E.ctx, s)):
            continue
        c = E.g.devolve(s, to='hand')
        if to == 'deck':
            E.op.hand.remove(c)
            E.op.deck.append(c)
    if to == 'deck':
        E.g.shuffle(E.opp)


@pattern(r"Devolve each of your opponent's evolved Pokémon by (putting|shuffling) the highest Stage Evolution card on it into your opponent's (hand|deck)")
def _(m):
    to = m.group(2)
    return lambda E: _devolve(E, list(E.op.in_play()), to)


@pattern(r"Devolve 1 of your opponent's evolved Pokémon by (putting|shuffling) the highest Stage Evolution card on it into your opponent's (hand|deck)")
def _(m):
    to = m.group(2)

    def step(E):
        c = [s for s in E.op.in_play() if s.evolved]
        if not c:
            return
        s = yield from E.g.choose_slot(E.p, c, 'devolve', 'Desevoluir qual Pokémon?', E.card)
        _devolve(E, [s], to)
    return step


@pattern(r"(?:Devolve it|devolve it) by putting the highest Stage Evolution card on it into your opponent's hand")
def _(m):
    return lambda E: _devolve(E, [E.opp_active()] if E.opp_active() else [], 'hand')


# ====================================================================== embaralhar / devolver Pokémon
@pattern(rf"Choose {NUMW} of your opponent's (Benched )?Pokémon")
def _(m):
    k, bench = num(m.group(1)), bool(m.group(2))

    def step(E):
        chosen = []
        for _ in range(k):
            c = [s for s in (E.op.bench if bench else E.op.in_play()) if s not in chosen]
            if not c:
                break
            chosen.append((yield from E.g.choose_slot(E.p, c, 'target', 'Escolha um Pokémon do oponente', E.card)))
        E.data['chosen'] = chosen
    return step


@pattern(r"Shuffle (?:that Pokémon|those Pokémon) and all attached cards into (?:their|your opponent's) deck")
def _(m):
    def step(E):
        for s in E.data.get('chosen', []):
            if E.g.in_play(s) and not E.g.effects_prevented(E.ctx, s):
                E.g.remove_slot(s, to='deck')
        yield from E.g._promote_if_needed()
    return step


@pattern(r"Shuffle 1 of your opponent's Benched Pokémon and all attached cards into their deck")
def _(m):
    def step(E):
        if not E.op.bench:
            return
        s = yield from E.g.choose_slot(E.p, E.op.bench, 'target', 'Embaralhar qual Pokémon do Banco?', E.card)
        if not E.g.effects_prevented(E.ctx, s):
            E.g.remove_slot(s, to='deck')
    return step


@pattern(r"If you do, shuffle all of your opponent's Benched Pokémon that you didn't choose, and all cards attached to those Pokémon, into their deck")
def _(m):
    def step(E):
        keep = E.data.get('chosen', [])
        if len(keep) < 3:
            return
        for s in list(E.op.bench):
            if s not in keep and not E.g.effects_prevented(E.ctx, s):
                E.g.remove_slot(s, to='deck')
    return step


@pattern(r"Shuffle 1 of your Benched Pokémon and all attached cards into your deck")
def _(m):
    def step(E):
        if not E.me.bench:
            return
        s = yield from E.g.choose_slot(E.p, E.me.bench, 'target', 'Embaralhar qual Pokémon do Banco?', E.card)
        E.g.remove_slot(s, to='deck')
    return step


@pattern(r"Put 1 of your Benched Pokémon and all attached cards into your hand")
def _(m):
    def step(E):
        if not E.me.bench:
            return
        s = yield from E.g.choose_slot(E.p, E.me.bench, 'target', 'Devolver qual Pokémon do Banco à mão?', E.card)
        E.g.remove_slot(s, to='hand')
    return step


@pattern(r"You may put this Pokémon into your hand")
def _(m):
    def step(E):
        if E.g.in_play(E.slot) and (yield from E.g.yes_no(E.p, 'Devolver este Pokémon à mão?', source=E.card)):
            E.g.remove_slot(E.slot, to='hand')
            yield from E.g._promote_if_needed()
    return step


@pattern(r"Discard this Pokémon and all attached cards")
def _(m):
    def step(E):
        E.g.remove_slot(E.slot, to='discard')
        yield from E.g._promote_if_needed()
    return step


@pattern(r"If you do, discard your opponent's Active Pokémon and all attached cards")
def _(m):
    def step(E):
        t = E.opp_active()
        if E.data.get('did') and t is not None and not E.g.effects_prevented(E.ctx, t):
            E.g.remove_slot(t, to='discard')
            yield from E.g._promote_if_needed()
    return step


@pattern(r"Put 2 (\w+) Energy attached to this Pokémon into your hand")
def _(m):
    code = NAME_TO_TYPE[m.group(1)]

    def step(E):
        got = yield from E.g.choose_cards(E.p, [e for e in E.slot.energy if e.d.provides == code], 2, 2, 'pick',
                                          'Energias para a mão', E.card, key=lambda c: c.uid)
        for e in got:
            E.slot.energy.remove(e)
            E.me.hand.append(e)
    return step


@pattern(r"(?:You may )?[Pp]ut (\d+) Energy attached to your opponent's Active (Stage 2 )?Pokémon into their hand")
def _(m):
    n = int(m.group(1))
    st2 = bool(m.group(2))

    def step(E):
        t = E.opp_active()
        if t is None or (st2 and t.d.stage != 2) or E.g.effects_prevented(E.ctx, t) or len(t.energy) < 1:
            return
        if m.group(0).startswith('You may') and not (yield from E.g.yes_no(E.p, 'Devolver Energias à mão do oponente?',
                                                                              source=E.card)):
            return
        k = min(n, len(t.energy))
        got = yield from E.g.choose_cards(E.p, t.energy, k, k, 'pick', 'Energias do oponente para a mão dele', E.card,
                                          key=lambda c: c.uid)
        for e in got:
            t.energy.remove(e)
            E.op.hand.append(e)
    return step


# ====================================================================== frases compostas ("A, and B")
SPLIT_RE = re.compile(r', and |,? and (?=(?:this attack|place|put|knock out|your opponent|make|have|discard|draw|heal|the new|that pokémon|it\b|take|attach|move|switch|shuffle|search|flip|this pokémon)\b)', re.I)


def register_multi():
    """Registrado por último: divide 'A, and B' em duas frases já reconhecidas."""
    from .compiler import PATTERNS, compile_sentence

    def builder(m):
        s = m.group(1)
        for sp in SPLIT_RE.finditer(s):
            a, b = cap(s[:sp.start()]), cap(s[sp.end():].rstrip('.'))
            try:
                ra, rb = compile_sentence(a), compile_sentence(b)
            except Unparsed:
                continue
            if isinstance(ra, dict) or isinstance(rb, dict):
                continue
            has_pre_b = any(ph == 'pre' for ph, _ in rb)
            return [('pre' if has_pre_b else ph, f) for ph, f in ra] + list(rb)
        raise Unparsed(s)
    PATTERNS.append((re.compile(r'^(.+?)\.?$'), builder, 'multi'))


# ====================================================================== mais ataques
@pattern(r"Your opponent flips a coin for each of their Benched Pokémon", 'pre')
def _(m):
    def step(E):
        n = len(E.op.bench)
        h = E.g.flips(n)
        E.data.update(heads_n=h, tails_n=n - h, heads=h > 0)
    step.est = lambda E, d: (E.data.update(tails_n=len(E.op.bench) / 2) or d)
    return step


@pattern(r"This attack does (\d+) damage to your opponent's Active Pokémon for each tails", 'pre')
def _(m):
    n = int(m.group(1))
    return _dmg_set(lambda E: n * E.data.get('tails_n', 0))


@pattern(r"For each tails, discard (an|\d+) Energy from this Pokémon")
def _(m):
    k = 1 if m.group(1) == 'an' else int(m.group(1))

    def step(E):
        t = E.data.get('tails_n', 0)
        if t:
            yield from lib.discard_energy_from(E.g, E.p, E.slot, k * t, None, E.ctx, E.card, units=True)
    return step


@pattern(r"Choose 1 of your opponent's Pokémon and flip a coin for each of your Pokémon in play that has \"(.+)\" in its name", 'pre')
def _(m):
    part = m.group(1)

    def step(E):
        t = yield from E.g.choose_slot(E.p, E.op.in_play(), 'damage_target', 'Escolha o alvo', E.card)
        n = sum(1 for s in E.me.in_play() if part in s.name)
        h = E.g.flips(n)
        E.data.update(chosen_target=t, heads_n=h, tails_n=n - h, heads=h > 0)
    return step


@pattern(r"This attack does (\d+) damage to the chosen Pokémon for each heads", 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        E.ctx.damage = 0
        t = E.data.get('chosen_target')
        if t is not None and E.data.get('heads_n'):
            E.g.deal_attack_damage(E.ctx, t, n * E.data['heads_n'])
    step.est = lambda E, d: n
    return step


@pattern(r"For each of your opponent's Pokémon, flip a coin", 'pre')
def _(m):
    def step(E):
        E.data['hit_list'] = [s for s in list(E.op.in_play()) if E.g.flip()]
        E.data['heads'] = bool(E.data['hit_list'])
    return step


@pattern(r"This attack does (\d+) damage to that Pokémon", 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        E.ctx.damage = 0
        for s in E.data.get('hit_list', []):
            E.g.deal_attack_damage(E.ctx, s, n)
    step.est = lambda E, d: n
    return step


@pattern(r"Choose 1 of your opponent's Pokémon (\d+) times", 'pre')
def _(m):
    k = int(m.group(1))

    def step(E):
        E.ctx.damage = 0
        E.data['picks'] = []
        for _ in range(k):
            c = E.op.in_play()
            if not c:
                break
            E.data['picks'].append((yield from E.g.choose_slot(E.p, c, 'damage_target', f'Alvo {len(E.data["picks"]) + 1}/{k}', E.card)))
    return step


@pattern(r"For each time you chose a Pokémon, do (\d+) damage to it", 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        for s in E.data.get('picks', []):
            if E.g.in_play(s):
                E.data.setdefault('oil', []).append((s, n))
    return step


@pattern(r"This damage isn't affected by Weakness or Resistance", 'pre')
def _(m):
    def step(E):
        saved = (E.ctx.ignore_weakness, E.ctx.ignore_resistance)
        E.ctx.ignore_weakness = E.ctx.ignore_resistance = True
        # ruling 2161: soma por Pokémon antes de aplicar modificadores (Granite Cave etc.)
        tot = {}
        for s, n in E.data.pop('oil', []):
            tot[s] = tot.get(s, 0) + n
        for s, n in tot.items():
            if E.g.in_play(s):
                E.g.deal_attack_damage(E.ctx, s, n)
        E.ctx.ignore_weakness, E.ctx.ignore_resistance = saved
    return step


@pattern(r"This attack does (\d+) damage to each Pokémon that has any damage counters on it, except for this Pokémon", 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        E.ctx.damage = 0
        for s in list(E.me.in_play() + E.op.in_play()):
            if s is not E.slot and s.damage > 0:
                E.g.deal_attack_damage(E.ctx, s, n)
    step.est = lambda E, d: n
    return step


@pattern(r"This attack does (\d+) damage to each of your opponent's Pokémon ex and Pokémon V", 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        E.ctx.damage = 0
        for s in list(E.op.in_play()):
            if s.d.is_ex or 'v' in s.d.tags:
                E.g.deal_attack_damage(E.ctx, s, n)
    step.est = lambda E, d: n
    return step


@pattern(r"This attack also does (\d+) damage to each of your (.+?) and (.+?)")
def _(m):
    n = int(m.group(1))
    names = {m.group(2), m.group(3)}

    def step(E):
        for s in list(E.me.in_play()):
            if s.name in names:
                E.g.deal_attack_damage(E.ctx, s, n)
    return step


@pattern(r"Move all Energy from this Pokémon to your Benched Pokémon in any way you like")
def _(m):
    def step(E):
        if not E.me.bench:
            return
        for e in list(E.slot.energy):
            t = yield from E.g.choose_slot(E.p, E.me.bench, 'attach_target', f'Mover {e.name} para', E.card,
                                           energy=e.d.provides)
            E.slot.energy.remove(e)
            t.energy.append(e)
    return step


@pattern(r"Discard (an|\d+) Energy from your opponent's Active (Stage 2 )?Pokémon( ex)?")
def _(m):
    k = 1 if m.group(1) == 'an' else int(m.group(1))
    ex = bool(m.group(3))

    def step(E):
        t = E.opp_active()
        if t is None or (ex and not t.d.is_ex) or E.g.effects_prevented(E.ctx, t):
            return
        yield from lib.discard_energy_from(E.g, E.p, t, k, None, None, E.card)
    return step


@pattern(r"Discard an? ({0}) Energy from your opponent's Active Pokémon".format(TYPE_WORDS))
def _(m):
    code = NAME_TO_TYPE[m.group(1)]

    def step(E):
        t = E.opp_active()
        if t is None or E.g.effects_prevented(E.ctx, t):
            return
        def pred(e):   # ruling 2194: Energia Especial que fornece o tipo (Prism em Básico, Legacy) também conta
            return any(code in u for c, us in E.g.energy_units(t) if c is e for u in us)
        yield from lib.discard_energy_from(E.g, E.p, t, 1, pred, None, E.card)
    return step


@pattern(r"Discard an Energy from (?:that|the Defending) Pokémon")
def _(m):
    def step(E):
        t = E.opp_active()
        if t is None or E.g.effects_prevented(E.ctx, t):
            return
        yield from lib.discard_energy_from(E.g, E.p, t, 1, None, None, E.card)
    return step


@pattern(r"Knock Out (?:1 of )?your opponent's (Active|Benched) Basic Pokémon")
def _(m):
    active = m.group(1) == 'Active'

    def step(E):
        if active:
            t = E.opp_active()
            if t is not None and t.d.stage == 0:
                knock_out(E, t)
            return
        c = [s for s in E.op.bench if s.d.stage == 0]
        if c:
            s = yield from E.g.choose_slot(E.p, c, 'ko_target', 'Nocautear qual Pokémon do Banco?', E.card)
            knock_out(E, s)
    return step


@pattern(r"If you do, heal all damage from that Pokémon|Heal all damage from that Pokémon")
def _(m):
    return lambda E: E.g.heal(E.data['that'], 9999) if E.data.get('that') else None


@pattern(r"Discard that Stadium")
def _(m):
    def step(E):
        if E.g.stadium is not None:
            yield from E.g.discard_stadium()
            E.data['did'] = True
    return step


@pattern(r"If your opponent has a Stadium in play, discard it")
def _(m):
    def step(E):
        E.data['did'] = False
        st = E.g.stadium
        if st is not None and st.owner == E.opp:
            yield from E.g.discard_stadium()
            E.data['did'] = True
    return step


@pattern(r"If you played an Ancient Supporter card from your hand during this turn, discard (\d+) more cards in this way")
def _(m):
    n = int(m.group(1))

    def step(E):
        from ..carddb import db
        played = [d for x in E.me.played for d in db().named(x)]
        if any(d.is_supporter and 'ancient' in d.tags for d in played):
            lib.mill(E.g, E.opp, n)
    return step


@pattern(rf"[Yy]our opponent discards {NUMW} more cards?")
def _(m):
    n = num(m.group(1))
    return lambda E: E.g.discard_from_hand(E.opp, n, source=E.card)


@pattern(r"[Tt]ake (a|\d+) Prize cards?")
def _(m):
    n = 1 if m.group(1) == 'a' else int(m.group(1))
    return lambda E: E.g.take_prizes(E.p, n)


@pattern(r"Shuffle your hand into your deck")
def _(m):
    return lambda E: E.g.hand_to_deck(E.p)


@pattern(r"Put a number of cards up to the number of heads from your discard pile into your hand")
def _(m):
    def step(E):   # ruling 2199: pega até o número de caras, no mínimo 1 se possível
        k = E.data.get('heads_n', 0)
        yield from lib.recover(E.g, E.p, lambda c: True, k, 'hand', E.card, min_n=min(k, len(E.me.discard)))
    return step


@pattern(rf"Search your deck for an amount of Basic (?:({TYPE_WORDS}) )?Energy up to the number of heads and attach it to this Pokémon")
def _(m):
    code = NAME_TO_TYPE[m.group(1)] if m.group(1) else None

    def step(E):
        pred = lambda c: c.d.basic_energy and (code is None or c.d.provides == code)
        yield from lib.search_attach(E.g, E.p, pred, E.data.get('heads_n', 0), lambda: [E.slot], E.card)
    return step


@pattern(r"For each heads, search your deck for up to (\d+) Basic Energy cards and attach them to your Pokémon in any way you like")
def _(m):
    k = int(m.group(1))

    def step(E):
        yield from lib.search_attach(E.g, E.p, lambda c: c.d.basic_energy, k * E.data.get('heads_n', 0),
                                     lambda: E.me.in_play(), E.card)
    return step


@pattern(rf"Attach (?:an amount|a number) of Basic (?:({TYPE_WORDS}) )?Energy(?: cards)? up to the number of heads from your discard pile to your Benched Pokémon in any way you like")
def _(m):
    code = NAME_TO_TYPE[m.group(1)] if m.group(1) else None

    def step(E):
        pred = lambda c: c.d.basic_energy and (code is None or c.d.provides == code)
        yield from lib.attach_from_discard(E.g, E.p, pred, E.data.get('heads_n', 0), lambda: list(E.me.bench), E.card)
    return step


@pattern(r"Attach up to (\d+) Energy cards from your opponent's discard pile to their Pokémon in any way you like")
def _(m):
    n = int(m.group(1))

    def step(E):
        got = yield from E.g.choose_cards(E.p, [c for c in E.op.discard if c.d.kind == 'energy'], n, 0, 'pick_energy',
                                          'Energias do descarte dele', E.card)
        for c in got:
            E.op.discard.remove(c)
        E.op.limbo.extend(got)
        for c in got:
            slots = [s for s in E.op.in_play() if E.g.can_attach_energy(E.opp, c, s)]
            if not slots:
                E.op.limbo.remove(c)
                E.op.discard.append(c)
                continue
            s = yield from E.g.choose_slot(E.p, slots, 'attach_target', f'Ligar {c.name} (do descarte dele) em', E.card)
            E.op.limbo.remove(c)
            yield from E.g.attach_energy(E.opp, c, s)
    return step


def _typed_attach(E, types, source_zone, remove_from_zone, targets, shuffle):
    """Anexa até 1 Energia Básica de cada tipo de `types` (de `source_zone`) a Pokémon de `targets`."""
    for t in types:
        pool = [c for c in source_zone() if c.d.basic_energy and c.d.provides == t]
        if not pool:
            continue
        got = yield from E.g.choose_cards(E.p, pool, 1, 0, 'search_energy', f'Energia {t} para ligar', E.card)
        for c in got:
            remove_from_zone(c)
        yield from lib.attach_cards(E.g, E.p, got, targets, E.card)
    if shuffle:
        E.g.shuffle(E.p)


@pattern(r"Search your deck for a Basic (\w+) Energy card, a Basic (\w+) Energy card, or 1 of each and attach them to your (\w+) Pokémon and (\w+) Pokémon in any way you like")
def _(m):
    types = [NAME_TO_TYPE[m.group(1)], NAME_TO_TYPE[m.group(2)]]
    ts = {NAME_TO_TYPE[m.group(3)], NAME_TO_TYPE[m.group(4)]}

    def step(E):
        yield from _typed_attach(E, types, lambda: E.me.deck, lambda c: E.me.deck.remove(c),
                                 lambda: [s for s in E.me.in_play() if set(E.g.types(s)) & ts] , True)
    return step


@pattern(r"Attach a Basic (\w+) Energy card, a Basic (\w+) Energy card, or 1 of each from your hand to your Pokémon in any way you like")
def _(m):
    types = [NAME_TO_TYPE[m.group(1)], NAME_TO_TYPE[m.group(2)]]

    def step(E):
        yield from _typed_attach(E, types, lambda: E.me.hand, lambda c: E.me.hand.remove(c),
                                 lambda: E.me.in_play(), False)
    return step


@pattern(r"Search your deck for up to (\d+) Basic Energy cards of different types and attach them to your (Tera )?Pokémon in any way you like")
def _(m):
    n = int(m.group(1))
    tera = bool(m.group(2))

    def step(E):
        used = set()
        got_all = []
        for _ in range(n):
            pool = [c for c in E.me.deck if c.d.basic_energy and c.d.provides not in used]
            got = yield from E.g.choose_cards(E.p, pool, 1, 0, 'search_energy', 'Energia de tipo diferente', E.card)
            if not got:
                break
            E.me.deck.remove(got[0])
            E.me.limbo.append(got[0])
            used.add(got[0].d.provides)
            got_all.append(got[0])
        for c in got_all:
            E.me.limbo.remove(c)
        yield from lib.attach_cards(E.g, E.p, got_all,
                                    lambda: [s for s in E.me.in_play() if not tera or 'tera' in s.d.tags], E.card)
        E.g.shuffle(E.p)
    return step


@pattern(r"For each of your Benched Pokémon, search your deck for a Basic (\w+) Energy card and attach it to that Pokémon")
def _(m):
    code = NAME_TO_TYPE[m.group(1)]

    def step(E):
        for s in list(E.me.bench):
            pool = [c for c in E.me.deck if c.d.basic_energy and c.d.provides == code]
            got = yield from E.g.choose_cards(E.p, pool, 1, 0, 'search_energy', f'Energia para {s.name}', E.card)
            for c in got:
                E.me.deck.remove(c)
                yield from E.g.attach_energy(E.p, c, s)
        E.g.shuffle(E.p)
    return step


@pattern(r"Choose Basic Lightning Energy cards from your discard pile up to the amount of Energy attached to all of your opponent's Pokémon and attach them to your Lightning Pokémon in any way you like")
def _(m):
    def step(E):
        n = sum(E.g.energy_count(s) for s in E.op.in_play())
        yield from lib.attach_from_discard(E.g, E.p, lambda c: c.d.basic_energy and c.d.provides == 'L', n,
                                           lambda: [s for s in E.me.in_play() if E.g.has_type(s, 'L')], E.card)
    return step


@pattern(r"Each player may attach up to (\d+) Basic Energy cards from their hand to their Pokémon in any way they like")
def _(m):
    n = int(m.group(1))

    def step(E):
        # ruling 2353: o oponente decide primeiro, mas a colocação é simultânea -- todas as escolhas (cartas e
        # alvos) são feitas antes de qualquer Energia ser ligada
        plans = []
        for who in (E.opp, E.p):
            pl = E.g.players[who]
            got = yield from E.g.choose_cards(who, [c for c in pl.hand if c.d.basic_energy], n, 0, 'attach_from_hand',
                                              'Energias da mão para ligar', E.card)
            for c in got:
                pl.hand.remove(c)
                pl.limbo.append(c)
            for c in got:
                slots = [s for s in pl.in_play() if E.g.can_attach_energy(who, c, s)]
                if not slots:
                    pl.limbo.remove(c)
                    pl.hand.append(c)
                    continue
                s = yield from E.g.choose_slot(who, slots, 'attach_target', f'Ligar em: {c.name}', E.card,
                                               energy=c.d.provides)
                plans.append((who, c, s))
        for who, c, s in plans:
            E.g.players[who].limbo.remove(c)
            # ruling 2354: Unaware (Skeledirge) previne o efeito do ataque; a Energia é descartada depois da escolha
            if who != E.p and E.slot is not None and E.g.effects_prevented_from(E.p, E.slot, s):
                E.g.players[who].discard.append(c)
                E.g.say(f'{c.name} foi descartada (efeito prevenido em {s.name})')
                continue
            yield from E.g.attach_energy(who, c, s, from_hand=False)
    return step


@pattern(r"Your opponent does this first")
def _(m):
    return None


@pattern(r"(?:Before doing damage, )?[Yy]ou may attach any number of Basic (\w+) Energy cards from your hand to this Pokémon", 'pre')
def _(m):
    code = NAME_TO_TYPE[m.group(1)]

    def step(E):
        pool = [c for c in E.me.hand if c.d.basic_energy and c.d.provides == code]
        got = yield from E.g.choose_cards(E.p, pool, len(pool), 0, 'attach_from_hand', 'Energias para ligar', E.card)
        for c in got:
            E.me.hand.remove(c)
        yield from lib.attach_cards(E.g, E.p, got, lambda: [E.slot], E.card)
    return step


@pattern(r"You may put all Energy attached to this Pokémon into your hand to have this attack do (\d+) more damage", 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        if not E.slot.energy:
            return
        if not (yield from E.g.yes_no(E.p, f'Devolver todas as Energias à mão para +{n} de dano?', source=E.card)):
            return
        for e in list(E.slot.energy):
            E.slot.energy.remove(e)
            E.me.hand.append(e)
        E.ctx.damage += n
    step.est = lambda E, d: d + n
    return step


@pattern(r"You may (discard all Energy from this Pokémon|shuffle all Energy attached to this Pokémon into your deck) and have this attack do (\d+) more damage", 'pre')
def _(m):
    shuffle = m.group(1).startswith('shuffle')
    n = int(m.group(2))

    def step(E):
        if not E.slot.energy:
            return
        if not (yield from E.g.yes_no(E.p, f'Perder todas as Energias para +{n} de dano?', source=E.card)):
            return
        if shuffle:
            for e in list(E.slot.energy):
                E.slot.energy.remove(e)
                E.me.deck.append(e)
            E.g.shuffle(E.p)
        else:
            E.g.discard_energy(E.slot, list(E.slot.energy), E.ctx)
        E.ctx.damage += n
    step.est = lambda E, d: d + n
    return step


@pattern(r"Shuffle all Energy attached to this Pokémon into your deck")
def _(m):
    def step(E):
        for e in list(E.slot.energy):
            E.slot.energy.remove(e)
            E.me.deck.append(e)
        E.g.shuffle(E.p)
    return step


@pattern(r"Discard up to (\d+) Energy cards? from this Pokémon, and this attack does (\d+) damage for each card you discarded in this way", 'pre')
def _(m):
    k, n = int(m.group(1)), int(m.group(2))

    def step(E):
        got = yield from lib.discard_energy_from(E.g, E.p, E.slot, k, None, E.ctx, E.card)
        E.ctx.damage = n * len(got)
    step.est = lambda E, d: n * min(k, len(E.slot.energy))
    return step


@pattern(r"Attach an Energy card from your hand to your Active (.*?)Pokémon")
def _(m):
    f = slot_filter(m.group(1) + 'Pokémon')

    def step(E):
        a = E.me.active
        if a is None or not f(E.g, a):
            return
        got = yield from E.g.choose_cards(E.p, [c for c in E.me.hand if c.d.kind == 'energy'], 1, 0, 'attach_from_hand',
                                          'Energia da mão para ligar', E.card)
        for c in got:
            E.me.hand.remove(c)
            yield from E.g.attach_energy(E.p, c, a, from_hand=True)
    return step


# ====================================================================== custo e uso do ataque (flags)
def _slot_cond(text):
    c = cond_expr(text)
    from .compiler import Exec

    def f(g, slot):
        return c(Exec(g, slot.owner, slot=slot))
    return f


@pattern(r"If (this Pokémon .+?), this attack can be used for ({0})".format(TYPE_WORDS), 'flag')
def _(m):
    f = _slot_cond(m.group(1))
    code = NAME_TO_TYPE[m.group(2)]
    return {'cost_mod': lambda g, slot, cost: [code] if f(g, slot) else cost}


@pattern(r"If (this Pokémon .+?), ignore all Energy in this attack's cost", 'flag')
def _(m):
    f = _slot_cond(m.group(1))
    return {'cost_mod': lambda g, slot, cost: [] if f(g, slot) else cost}


@pattern(r"You can use this attack only if this Pokémon used (.+?) during your last turn", 'flag')
def _(m):
    nm = m.group(1)
    return {'can_use': lambda g, s: (g.turn - 2, nm) in s.flags.get('atk_log', [])}


@pattern(r"If 1 of your Pokémon used (.+?) during your last turn, this attack can't be used", 'flag')
def _(m):
    nm = m.group(1)
    return {'can_use': lambda g, s: not any(t == g.turn - 2 and n == nm for t, _, n in g.players[s.owner].attack_log)}


@pattern(r"If you go second, you can't use this attack during your first turn", 'flag')
def _(m):
    return {'can_use': lambda g, s: g.players[s.owner].went_first or not g.first_turn(s.owner)}


@pattern(r"This Pokémon can't use (.+?) again until it leaves the Active Spot")
def _(m):
    name = m.group(1)

    def step(E):
        s = E.slot
        E.g.add_effect(f'não pode usar {name}', E.p, {'can_attack': lambda g, src, slot, attack, s=s:
                                                      False if slot is s and attack.name == name else None},
                       target=s, duration=10 ** 6, while_active=True)
    return step


# ====================================================================== sobras
@pattern(r"That attack doesn't happen")
def _(m):
    return None


@pattern(r"Discard your opponent's Active Pokémon and all attached cards")
def _(m):
    def step(E):
        t = E.opp_active()
        if t is not None and not E.g.effects_prevented(E.ctx, t):
            E.g.remove_slot(t, to='discard')
            yield from E.g._promote_if_needed()
    return step


@pattern(r"Shuffle all of your opponent's Benched Pokémon that you didn't choose, and all cards attached to those Pokémon, into their deck")
def _(m):
    def step(E):
        keep = E.data.get('chosen', [])
        if len(keep) < 3:
            return
        for s in list(E.op.bench):
            if s not in keep and not E.g.effects_prevented(E.ctx, s):
                E.g.remove_slot(s, to='deck')
    return step


@pattern(r"If you use this attack when you have exactly (\d+) Prize cards? remaining, you win this game")
def _(m):
    n = int(m.group(1))

    def step(E):
        if len(E.me.prizes) == n:
            from ..core import GameOver
            raise GameOver(E.p, f'{E.card.name if E.card else "ataque"}: vitória direta')
    return step


@pattern(r"Put this Pokémon and all attached cards into your deck")
def _(m):
    return lambda E: E.g.remove_slot(E.slot, to='deck')


@pattern(r"During your opponent's next turn, whenever they try to use a Trainer card from their hand, they flip a coin")
def _(m):
    def step(E):
        o = E.opp
        E.g.add_effect('Punho Trêmulo', E.p, {'trainer_fizzle': lambda g, src, player, card, o=o:
                                              player == o and not g.flip()}, duration='opp_next_turn')
    return step


@pattern(r"Your opponent discards that Trainer card instead of using it")
def _(m):
    return None


def maybe_reroll(E):
    """Backtrack Badge: depois de jogar as moedas de um ataque, 1x por turno pode ignorar TODOS os resultados e jogar de novo.
    Devolve True se aceitou (quem chama refaz a fase 'pre'). Não vale para moedas fora do ataque (ex.: Confusão)."""
    if E.ctx is None or E.slot is None or not E.g.has_type(E.slot, 'C'):
        return False
    badge = next((t for t in E.slot.tools if t.name == 'Backtrack Badge'), None)
    key = f'Backtrack Badge:{badge.uid}' if badge is not None else None
    if badge is None or key in E.me.ability_keys:
        return False
    if (yield from E.g.yes_no(E.p, 'Backtrack Badge: ignorar as moedas e jogar de novo?', source=badge)):
        E.me.ability_keys.add(key)
        return True
    return False
