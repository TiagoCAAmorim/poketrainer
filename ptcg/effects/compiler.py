"""Compilador de texto de carta → efeito executável.

Cada frase do texto oficial (em inglês) é reconhecida por um padrão e vira um passo.
Passos de ataque têm fase 'pre' (antes do dano: moedas, modificadores de dano, escolha de alvos)
ou 'post' (depois do dano: condições, cura, compra, descarte...). Frases não reconhecidas são
registradas em `unparsed` e a carta fica marcada como 'partial'/'missing' no relatório.
"""
from __future__ import annotations

import re

from ..core import AbilityImpl, AttackImpl, NAME_TO_TYPE, TrainerImpl
from ..engine import run
from . import lib
from .lib import TYPE_WORDS, card_filter, num, or_filter, slot_filter

NUMW = r'(\d+|a|an|one|two|three|four|five|six|seven|eight)'
COND_RE = r'(Asleep|Burned|Confused|Paralyzed|Poisoned)'


class Exec:
    """Contexto de execução de um efeito compilado."""

    def __init__(self, g, p, slot=None, ctx=None, card=None):
        self.g, self.p, self.ctx = g, p, ctx
        self.slot = slot if slot is not None else (ctx.attacker if ctx is not None else None)
        self.card = card if card is not None else (self.slot.top if self.slot is not None else None)
        self.data = {}

    @property
    def opp(self):
        return 1 - self.p

    @property
    def me(self):
        return self.g.players[self.p]

    @property
    def op(self):
        return self.g.players[1 - self.p]

    def opp_active(self):
        if self.ctx is not None and self.ctx.defender is not None and self.g.in_play(self.ctx.defender):
            return self.ctx.defender
        return self.op.active

    @property
    def kind(self):
        return 'attack' if self.ctx is not None else ('ability' if self.slot is not None else 'trainer')


class Unparsed(Exception):
    pass


# ======================================================================== expressões
def count_expr(ph: str):
    """'Energy attached to this Pokémon' → f(E) -> int"""
    ph = ph.strip().rstrip('.').strip()
    ph = re.sub(r'\s+', ' ', ph)
    T = None
    m = re.match(rf'^({TYPE_WORDS}) (.*)$', ph)
    if m and 'Pokémon' not in m.group(1):
        T, rest = NAME_TO_TYPE[m.group(1)], m.group(2)
    else:
        rest = ph
    if rest in ('Energy attached to this Pokémon', 'Energy card attached to this Pokémon'):
        return lambda E: E.g.energy_count(E.slot, T)
    if rest == "Energy attached to your opponent's Active Pokémon":
        return lambda E: E.g.energy_count(E.opp_active(), T) if E.opp_active() else 0
    if rest == 'Energy attached to both Active Pokémon':
        return lambda E: sum(E.g.energy_count(s, T) for s in (E.me.active, E.opp_active()) if s)
    if rest in ('Energy attached to all of your Pokémon', 'Energy attached to your Pokémon'):
        return lambda E: sum(E.g.energy_count(s, T) for s in E.me.in_play())
    if rest == "Energy attached to all of your opponent's Pokémon":
        return lambda E: sum(E.g.energy_count(s, T) for s in E.op.in_play())
    if rest == 'Energy attached to all of your Benched Pokémon':
        return lambda E: sum(E.g.energy_count(s, T) for s in E.me.bench)
    if T is None:
        if rest == 'damage counter on this Pokémon':
            return lambda E: E.slot.damage // 10
        if rest == "damage counter on your opponent's Active Pokémon":
            return lambda E: (E.opp_active().damage // 10) if E.opp_active() else 0
        if rest == "damage counter on all of your opponent's Pokémon":
            return lambda E: sum(s.damage // 10 for s in E.op.in_play())
        if rest == 'damage counter on all of your Benched Pokémon':
            return lambda E: sum(s.damage // 10 for s in E.me.bench)
        if rest in ('heads',):
            return lambda E: E.data.get('heads_n', 0)
        if rest in ('tails',):
            return lambda E: E.data.get('tails_n', 0)
        if rest == 'of your Benched Pokémon':
            return lambda E: len(E.me.bench)
        if rest == "of your opponent's Benched Pokémon":
            return lambda E: len(E.op.bench)
        if rest in ("Benched Pokémon", "Benched Pokémon both yours and your opponent's"):
            return lambda E: len(E.me.bench) + len(E.op.bench)
        if rest == 'of your Pokémon in play':
            return lambda E: len(E.me.in_play())
        if rest == 'Prize card your opponent has taken':
            return lambda E: E.g.prizes_taken(E.opp)
        if rest == 'Prize card you have taken':
            return lambda E: E.g.prizes_taken(E.p)
        if rest == 'card in your hand':
            return lambda E: len(E.me.hand)
        if rest == "card in your opponent's hand":
            return lambda E: len(E.op.hand)
        if rest in ('card you discarded in this way', 'Energy card you discarded in this way',
                    'card discarded in this way', 'Energy card discarded in this way'):
            return lambda E: E.data.get('discarded', 0)
        if rest == "Colorless in your opponent's Active Pokémon's Retreat Cost":
            return lambda E: E.g.retreat_cost(E.opp_active()) if E.opp_active() else 0
        if rest == 'Pokémon Tool attached to all of your Pokémon':
            return lambda E: sum(len(s.tools) for s in E.me.in_play())
        if rest == "Special Condition affecting your opponent's Active Pokémon":
            return lambda E: len(E.opp_active().conditions) if E.opp_active() else 0
        if rest in ('Energy card in your discard pile',):
            return lambda E: sum(1 for c in E.me.discard if c.d.kind == 'energy')
        m = re.match(r'^(.*) card in your discard pile$', rest)
        if m:
            f = card_filter(m.group(1))
            return lambda E: sum(1 for c in E.me.discard if f(c))
        m = re.match(r'^of your (.+?) in play$', rest)
        if m:
            sub = m.group(1)
            if 'Pokémon' in sub:
                f = slot_filter(sub)
                return lambda E: sum(1 for s in E.me.in_play() if f(E.g, s))
            names = [x.strip() for x in re.split(r' and | or ', sub)]
            return lambda E: sum(1 for s in E.me.in_play() if s.name in names)
        m = re.match(r'^of your Benched (.+)$', rest)
        if m:
            sub = m.group(1)
            if 'Pokémon' in sub:
                f = slot_filter(sub)
                return lambda E: sum(1 for s in E.me.bench if f(E.g, s))
            return lambda E: sum(1 for s in E.me.bench if s.name == sub)
    m = re.match(r'^(.+?) Pokémon in play$', ph)
    if m:
        f = slot_filter(m.group(1) + ' Pokémon')
        return lambda E: sum(1 for p in (0, 1) for s in E.g.players[p].in_play() if f(E.g, s))
    raise Unparsed(f'contagem: {ph}')


def opp_active_pred(desc: str):
    """predicado para 'is a Pokémon ex', 'is Poisoned', 'has an Ability'..."""
    d = desc.strip()
    if d in ('is a Pokémon ex', 'is a Pokémon ex or Pokémon V'):
        return lambda E, s: s.d.is_ex
    if d == 'is a Mega Evolution Pokémon ex':
        return lambda E, s: s.d.is_mega
    if d == 'is a Basic Pokémon':
        return lambda E, s: s.d.stage == 0
    if d == 'is an Evolution Pokémon':
        return lambda E, s: s.d.stage > 0
    m = re.match(r'^is a Stage (\d) Pokémon$', d)
    if m:
        st = int(m.group(1))
        return lambda E, s: s.d.stage == st
    m = re.match(rf'^is an? ({TYPE_WORDS}) Pokémon$', d)
    if m:
        t = NAME_TO_TYPE[m.group(1)]
        return lambda E, s: E.g.has_type(s, t)
    m = re.match(rf'^is {COND_RE}$', d)
    if m:
        c = lib.cond_word(m.group(1))
        return lambda E, s: c in s.conditions
    m = re.match(rf"^isn't {COND_RE}$", d)
    if m:
        c = lib.cond_word(m.group(1))
        return lambda E, s: c not in s.conditions
    if d == 'is affected by a Special Condition':
        return lambda E, s: bool(s.conditions)
    if d in ('already has any damage counters on it', 'has any damage counters on it', 'has damage counters on it'):
        return lambda E, s: s.damage > 0
    if d == 'has an Ability':
        return lambda E, s: E.g.has_ability(s)
    if d in ('has a Rule Box', 'is a Pokémon that has a Rule Box'):
        return lambda E, s: s.d.rule_box
    if d == 'is a Tera Pokémon':
        return lambda E, s: 'tera' in s.d.tags
    m = re.match(r'^has (\d+) or more Energy attached$', d)
    if m:
        n = int(m.group(1))
        return lambda E, s: E.g.energy_count(s) >= n
    if d == 'has any Special Energy attached':
        return lambda E, s: any(e.d.special_energy for e in s.energy)
    if d == 'has a Pokémon Tool attached':
        return lambda E, s: bool(s.tools)
    raise Unparsed(f'condição do Ativo: {d}')


def self_pred(desc: str):
    d = desc.strip()
    if d in ('has any damage counters on it', 'has damage counters on it'):
        return lambda E, s: s.damage > 0
    if d == 'has no damage counters on it':
        return lambda E, s: s.damage == 0
    m = re.match(r'^has (\d+) or more damage counters on it$', d)
    if m:
        n = int(m.group(1))
        return lambda E, s: s.damage >= 10 * n
    m = re.match(rf'^has any ({TYPE_WORDS}) Energy attached$', d)
    if m:
        t = NAME_TO_TYPE[m.group(1)]
        return lambda E, s: E.g.has_energy_type(s, t)
    if d == 'has any Special Energy attached':
        return lambda E, s: any(e.d.special_energy for e in s.energy)
    m = re.match(r'^has any (.+ Energy) attached$', d)
    if m:
        f = card_filter(m.group(1))
        return lambda E, s: any(f(e) for e in s.energy)
    if d in ('has a Pokémon Tool attached', 'has any Pokémon Tools attached'):
        return lambda E, s: bool(s.tools)
    if d == 'has any Energy attached':
        return lambda E, s: bool(s.energy)
    if d == 'has no Energy attached':
        return lambda E, s: not s.energy
    if d == 'is in the Active Spot':
        return lambda E, s: E.g.is_active(s)
    if d == 'is on your Bench':
        return lambda E, s: not E.g.is_active(s)
    if d == 'was healed during this turn':
        return lambda E, s: s.flags.get('healed_turn') == E.g.turn
    if d == 'moved from your Bench to the Active Spot this turn':
        return lambda E, s: s.flags.get('to_active_turn') == E.g.turn
    m = re.match(r'^has at least (\d+) extra Energy attached$', d)
    if m:
        n = int(m.group(1))
        return lambda E, s: E.g.energy_count(s) - len(E.ctx.attack.cost if E.ctx else []) >= n
    m = re.match(r'^evolved from (.+) during this turn$', d)
    if m:
        nm = m.group(1)
        return lambda E, s: s.turn_evolved == E.g.turn and len(s.cards) > 1 and s.cards[-2].name == nm
    raise Unparsed(f'condição deste Pokémon: {d}')


def cond_expr(ph: str):
    """Condição de 'If X, ...' → f(E) -> bool"""
    ph = ph.strip()
    m = re.match(r"^your opponent's Active Pokémon (.+)$", ph)
    if m:
        f = opp_active_pred(m.group(1))
        return lambda E: E.opp_active() is not None and f(E, E.opp_active())
    m = re.match(r"^the Defending Pokémon (.+)$", ph)
    if m:
        f = opp_active_pred(m.group(1))
        return lambda E: E.opp_active() is not None and f(E, E.opp_active())
    m = re.match(r'^this Pokémon (.+)$', ph)
    if m:
        f = self_pred(m.group(1))
        return lambda E: E.slot is not None and f(E, E.slot)
    if ph in ('any of your Pokémon were Knocked Out by damage from an attack during your opponent\'s last turn',
              "any of your Pokémon were Knocked Out by damage from an attack from your opponent's Pokémon during "
              "their last turn"):
        return lambda E: E.g.kod_last_turn(E.p, lambda e: e['by_attack'])
    if ph == "any of your Pokémon were Knocked Out during your opponent's last turn":
        return lambda E: E.g.kod_last_turn(E.p)
    m = re.match(r'^your opponent has (\d+) or fewer Prize cards remaining$', ph)
    if m:
        n = int(m.group(1))
        return lambda E: len(E.op.prizes) <= n
    m = re.match(r'^you have (\d+) or fewer Prize cards remaining$', ph)
    if m:
        n = int(m.group(1))
        return lambda E: len(E.me.prizes) <= n
    if ph == 'you have more Prize cards remaining than your opponent':
        return lambda E: len(E.me.prizes) > len(E.op.prizes)
    if ph == 'a Stadium is in play':
        return lambda E: E.g.stadium is not None
    m = re.match(r'^you played (.+?) from your hand during this turn$', ph)
    if m:
        nm = m.group(1)
        return lambda E: nm in E.me.played
    m = re.match(r'^your opponent has (\d+) or fewer cards in their hand$', ph)
    if m:
        n = int(m.group(1))
        return lambda E: len(E.op.hand) <= n
    m = re.match(r'^you have (\d+) or (?:more|fewer) cards in your hand$', ph)
    if m:
        n = int(m.group(1))
        more = 'more' in ph
        return lambda E: len(E.me.hand) >= n if more else len(E.me.hand) <= n
    m = re.match(r'^you have (?:any )?(.+?) (?:on your Bench|in play)$', ph)
    if m:
        sub = m.group(1)
        on_bench = 'Bench' in ph
        if 'Pokémon' in sub:
            f = slot_filter(sub)
            return lambda E: any(f(E.g, s) for s in (E.me.bench if on_bench else E.me.in_play()))
        names = [x.strip() for x in re.split(r' and | or ', sub)]
        return lambda E: any(s.name in names for s in (E.me.bench if on_bench else E.me.in_play()))
    m = re.match(r'^your opponent has any (.+?) in play$', ph)
    if m:
        f = slot_filter(m.group(1))
        return lambda E: any(f(E.g, s) for s in E.op.in_play())
    if ph == 'your Benched Pokémon have any damage counters on them':
        return lambda E: any(s.damage > 0 for s in E.me.bench)
    if ph == 'this Pokémon and your opponent\'s Active Pokémon have the same amount of Energy attached':
        return lambda E: E.opp_active() is not None and E.g.energy_count(E.slot) == E.g.energy_count(E.opp_active())
    m = re.match(r'^you have (\d+) or more Pokémon that have the (.+) Ability in your discard pile$', ph)
    if m:
        n, ab = int(m.group(1)), m.group(2)
        return lambda E: sum(1 for c in E.me.discard if c.d.kind == 'pokemon' and
                             any(a.name == ab for a in c.d.abilities)) >= n
    if ph == "any of your Pokémon in play are the same type as any of your opponent's Pokémon in play":
        return lambda E: bool({t for s in E.me.in_play() for t in E.g.types(s)} &
                              {t for s in E.op.in_play() for t in E.g.types(s)})
    m = re.match(r'^(.+?) are on your Bench$', ph)
    if m:
        names = [x.strip() for x in re.split(r',\s*|\s+and\s+', m.group(1)) if x.strip()]
        return lambda E: all(any(s.name == n for s in E.me.bench) for n in names)
    if ph == 'you go first':
        return lambda E: E.me.went_first
    if ph == 'you go second':
        return lambda E: not E.me.went_first
    raise Unparsed(f'condição: {ph}')


# ======================================================================== alvos
def target_slots(ph: str):
    """'1 of your Benched Pokémon' → (quem escolhe, f(E)->[slots], quantidade)"""
    ph = ph.strip()
    m = re.match(rf'^{NUMW} of (your|your opponent\'s) (Benched )?(.*?)Pokémon$', ph)
    if m:
        n = num(m.group(1))
        side = m.group(2)
        bench = bool(m.group(3))
        f = slot_filter(m.group(4) + 'Pokémon')

        def slots(E, side=side, bench=bench, f=f):
            pl = E.me if side == 'your' else E.op
            return [s for s in (pl.bench if bench else pl.in_play()) if f(E.g, s)]
        return n, slots
    raise Unparsed(f'alvo: {ph}')


def _active_or_self(ph):
    ph = ph.strip()
    if ph in ("your opponent's Active Pokémon", 'the Defending Pokémon', 'that Pokémon'):
        return lambda E: E.opp_active()
    if ph == 'this Pokémon':
        return lambda E: E.slot
    if ph == 'your Active Pokémon':
        return lambda E: E.me.active
    if ph == 'the new Active Pokémon':
        return lambda E: E.op.active
    raise Unparsed(f'referência: {ph}')


# ======================================================================== padrões de frase
PATTERNS = []


def pattern(rx, phase='post'):
    def deco(f):
        PATTERNS.append((re.compile('^' + rx + r'\.?$'), f, phase))
        return f
    return deco


def _dmg_add(fn_delta, est=None):
    def step(E):
        if E.ctx is not None:
            E.ctx.damage += fn_delta(E)
    step.est = est or (lambda E, d: d + fn_delta(E))
    return step


def _dmg_set(fn_val, est=None):
    def step(E):
        if E.ctx is not None:
            E.ctx.damage = fn_val(E)
    step.est = est or (lambda E, d: fn_val(E))
    return step


# --- moedas
@pattern(r'Flip a coin', 'pre')
def _(m):
    def step(E):
        h = E.g.flip()
        E.data['heads'] = h
        E.data['heads_n'] = int(h)
        E.data['tails_n'] = 1 - int(h)
    step.est = lambda E, d: (E.data.update(heads=True, heads_n=0.5, tails_n=0.5) or d)
    return step


@pattern(rf'Flip {NUMW} coins', 'pre')
def _(m):
    n = num(m.group(1))

    def step(E):
        h = E.g.flips(n)
        E.data['heads_n'] = h
        E.data['tails_n'] = n - h
        E.data['heads'] = h > 0
    step.est = lambda E, d: (E.data.update(heads_n=n / 2, tails_n=n / 2, heads=True) or d)
    return step


@pattern(r'Flip a coin until you get tails', 'pre')
def _(m):
    def step(E):
        h = E.g.flip_until_tails()
        E.data['heads_n'] = h
        E.data['heads'] = h > 0
    step.est = lambda E, d: (E.data.update(heads_n=1, heads=True) or d)
    return step


@pattern(r'Flip a coin for each (.+)', 'pre')
def _(m):
    cnt = count_expr(m.group(1))

    def step(E):
        n = cnt(E)
        h = E.g.flips(n)
        E.data['heads_n'] = h
        E.data['tails_n'] = n - h
    step.est = lambda E, d: (E.data.update(heads_n=cnt(E) / 2) or d)
    return step


@pattern(r'(?:If tails, )?[Tt]his attack does nothing', 'pre')
def _(m):
    def step(E):
        if E.ctx is not None:
            E.ctx.no_damage = True
            E.ctx.damage = 0
    step.est = lambda E, d: d * 0.5
    return step


# --- dano
@pattern(r'This attack does (\d+) more damage for each (.+)', 'pre')
def _(m):
    n, cnt = int(m.group(1)), count_expr(m.group(2))
    return _dmg_add(lambda E: n * cnt(E))


@pattern(r'This attack does (\d+) less damage for each (.+)', 'pre')
def _(m):
    n, cnt = int(m.group(1)), count_expr(m.group(2))
    return _dmg_add(lambda E: -n * cnt(E))


@pattern(r'This attack does (\d+) damage for each (.+)', 'pre')
def _(m):
    n, cnt = int(m.group(1)), count_expr(m.group(2))
    return _dmg_set(lambda E: n * cnt(E))


@pattern(r'(?:If heads, )?[Tt]his attack does (\d+) more damage', 'pre')
def _(m):
    n = int(m.group(1))
    return _dmg_add(lambda E: n)


@pattern(r'You may do (\d+) more damage', 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        if (yield from E.g.yes_no(E.p, f'Causar {n} de dano a mais?', source=E.card)):
            E.ctx.damage += n
            E.data['did'] = True
        else:
            E.data['did'] = False
    step.est = lambda E, d: d + n
    return step


@pattern(r"This attack's damage isn't affected by (.+)", 'flag')
def _(m):
    w = m.group(1)
    flags = {}
    if 'Weakness' in w:
        flags['ignore_weakness'] = True
    if 'Resistance' in w:
        flags['ignore_resistance'] = True
    if 'effects' in w:
        flags['ignore_effects'] = True
    return flags


@pattern(r'This Pokémon (?:also )?does (\d+) damage to itself')
def _(m):
    n = int(m.group(1))

    def step(E):
        E.g.deal_attack_damage(E.ctx, E.slot, n) if E.ctx else None
    return step


@pattern(r'This Pokémon also does (\d+) damage to itself for each damage counter on it')
def _(m):
    n = int(m.group(1))
    return lambda E: E.g.deal_attack_damage(E.ctx, E.slot, n * (E.slot.damage // 10))


@pattern(rf"This attack also does (\d+) damage to {NUMW} of your opponent's Benched Pokémon")
def _(m):
    n, k = int(m.group(1)), num(m.group(2))
    return lambda E: lib.bench_damage(E.g, E.ctx, k, n, 'opp')


@pattern(r"This attack also does (\d+) damage to each of your opponent's Benched Pokémon")
def _(m):
    n = int(m.group(1))
    return lambda E: lib.bench_damage(E.g, E.ctx, 99, n, 'opp')


@pattern(r'This attack also does (\d+) damage to each of your Benched Pokémon')
def _(m):
    n = int(m.group(1))
    return lambda E: lib.bench_damage(E.g, E.ctx, 99, n, 'me')


@pattern(rf'This attack also does (\d+) damage to {NUMW} of your Benched Pokémon')
def _(m):
    n, k = int(m.group(1)), num(m.group(2))
    return lambda E: lib.bench_damage(E.g, E.ctx, k, n, 'me', 'Escolha seu Pokémon do Banco')


@pattern(r'This attack also does (\d+) damage to each Benched Pokémon(?: both yours and your opponent\'s)?')
def _(m):
    n = int(m.group(1))

    def step(E):
        yield from lib.bench_damage(E.g, E.ctx, 99, n, 'opp')
        yield from lib.bench_damage(E.g, E.ctx, 99, n, 'me')
    return step


@pattern(rf"This attack does (\d+) damage to {NUMW} of your opponent's (Benched )?Pokémon", 'pre')
def _(m):
    n, k, bench = int(m.group(1)), num(m.group(2)), bool(m.group(3))

    def step(E):
        E.ctx.no_damage = False
        E.ctx.damage = 0
        op = E.op
        chosen = []
        for _ in range(k):
            cands = [s for s in (op.bench if bench else op.in_play()) if s not in chosen]
            if not cands:
                break
            s = yield from E.g.choose_slot(E.p, cands, 'damage_target', f'Causar {n} de dano em', E.card)
            chosen.append(s)
        for s in chosen:
            E.g.deal_attack_damage(E.ctx, s, n)
    step.est = lambda E, d: n
    return step


@pattern(r"This attack does (\d+) damage to each of your opponent's Pokémon( ex)?", 'pre')
def _(m):
    n, only_ex = int(m.group(1)), bool(m.group(2))

    def step(E):
        E.ctx.damage = 0
        for s in list(E.op.in_play()):
            if not only_ex or s.d.is_ex:
                E.g.deal_attack_damage(E.ctx, s, n)
    step.est = lambda E, d: n
    return step


@pattern(r'This attack does (\d+) damage to the new Active Pokémon', 'pre')
def _(m):
    n = int(m.group(1))

    def step(E):
        E.ctx.defender = E.op.active
        E.ctx.damage = n
    return step


# --- condições especiais
@pattern(rf"(?:Your opponent's Active Pokémon|The Defending Pokémon|That Pokémon) is now {COND_RE}(?:,? and {COND_RE})?")
def _(m):
    cs = [lib.cond_word(x) for x in m.groups() if x]

    def step(E):
        t = E.opp_active()
        for c in cs:
            E.g.add_condition(t, c, E.ctx)
    return step


@pattern(rf'This Pokémon is now {COND_RE}(?: and {COND_RE})?')
def _(m):
    cs = [lib.cond_word(x) for x in m.groups() if x]

    def step(E):
        for c in cs:
            E.g.add_condition(E.slot, c)
    return step


@pattern(rf"Make your opponent's Active Pokémon {COND_RE}")
def _(m):
    c = lib.cond_word(m.group(1))
    return lambda E: E.g.add_condition(E.op.active, c, E.ctx)


@pattern(r'This Pokémon recovers from all Special Conditions')
def _(m):
    return lambda E: E.slot.clear_conditions()


# --- cura
@pattern(r'Heal (\d+) damage from this Pokémon')
def _(m):
    n = int(m.group(1))
    return lambda E: E.g.heal(E.slot, n)


@pattern(r'Heal all damage from this Pokémon')
def _(m):
    return lambda E: E.g.heal(E.slot, 9999)


@pattern(r'Heal from this Pokémon the same amount of damage you did to your opponent\'s Active Pokémon')
def _(m):
    return lambda E: E.g.heal(E.slot, E.ctx.done_damage)


@pattern(r'Heal (\d+) damage from each of your (.*?)Pokémon')
def _(m):
    n = int(m.group(1))
    f = slot_filter(m.group(2) + 'Pokémon')
    return lambda E: [E.g.heal(s, n) for s in E.me.in_play() if f(E.g, s)]


@pattern(rf'Heal (\d+|all) damage from {NUMW} of your (Benched )?(.*?)Pokémon')
def _(m):
    n = 9999 if m.group(1) == 'all' else int(m.group(1))
    k, bench = num(m.group(2)), bool(m.group(3))
    f = slot_filter(m.group(4) + 'Pokémon')

    def step(E):
        done = []
        for _ in range(k):
            c = [s for s in (E.me.bench if bench else E.me.in_play()) if f(E.g, s) and s.damage > 0 and s not in done]
            if not c:
                break
            s = yield from E.g.choose_slot(E.p, c, 'heal_target', 'Curar qual Pokémon?', E.card)
            E.g.heal(s, n)
            done.append(s)
    return step


@pattern(r'Heal (\d+) damage from your Active Pokémon')
def _(m):
    n = int(m.group(1))
    return lambda E: E.g.heal(E.me.active, n) if E.me.active else None


# --- compra / mão
@pattern(rf'(?:Then, )?[Dd]raw {NUMW} cards?')
def _(m):
    n = num(m.group(1))
    return lambda E: E.g.draw(E.p, n)


@pattern(r'(?:You may )?[Dd]raw cards until you have (\d+) cards in your hand')
def _(m):
    n = int(m.group(1))
    return lambda E: E.g.draw_until(E.p, n)


@pattern(r'Each player draws a card')
def _(m):
    return lambda E: (E.g.draw(E.p, 1), E.g.draw(1 - E.p, 1))


@pattern(r'Shuffle your hand into your deck')
def _(m):
    return lambda E: E.g.hand_to_deck(E.p)


@pattern(rf'Discard your hand and draw {NUMW} cards')
def _(m):
    n = num(m.group(1))
    return lambda E: (E.g.discard_hand(E.p), E.g.draw(E.p, n))


@pattern(r'Discard a card from your hand')
def _(m):
    def step(E):
        got = yield from E.g.discard_from_hand(E.p, 1, source=E.card)
        E.data['did'] = bool(got)
    return step


@pattern(r'Your opponent reveals their hand')
def _(m):
    return lambda E: lib.reveal_hand(E.g, E.opp)


@pattern(r"Discard a random card from your opponent's hand")
def _(m):
    return lambda E: lib.opp_discards_random(E.g, E.p, 1)


@pattern(r"For each heads, discard a random card from your opponent's hand")
def _(m):
    return lambda E: lib.opp_discards_random(E.g, E.p, E.data.get('heads_n', 0))


@pattern(rf'Your opponent discards {NUMW} cards? from their hand')
def _(m):
    n = num(m.group(1))
    return lambda E: E.g.discard_from_hand(E.opp, n, source=E.card)


@pattern(r"Discard the top card of your opponent's deck")
def _(m):
    return lambda E: lib.mill(E.g, E.opp, 1)


@pattern(r"Discard the top (\d+) cards of your opponent's deck")
def _(m):
    n = int(m.group(1))
    return lambda E: lib.mill(E.g, E.opp, n)


@pattern(r"For each heads, discard the top card of your opponent's deck")
def _(m):
    return lambda E: lib.mill(E.g, E.opp, E.data.get('heads_n', 0))


@pattern(r'Discard the top (\d+|) ?cards? of your deck')
def _(m):
    n = int(m.group(1)) if m.group(1) else 1
    return lambda E: lib.mill(E.g, E.p, n)


# --- energia
@pattern(rf'Discard (an|{NUMW}|all) ?({TYPE_WORDS}|Basic|Special)? Energy from this Pokémon')
def _(m):
    raw = m.group(1)
    n = 99 if raw == 'all' else num(raw)
    t = m.group(3)
    pred = None
    if t in NAME_TO_TYPE:
        code = NAME_TO_TYPE[t]
        pred = lambda e, code=code: e.d.provides == code or e.d.special_energy
    elif t == 'Basic':
        pred = lambda e: e.d.basic_energy
    elif t == 'Special':
        pred = lambda e: e.d.special_energy

    def step(E):
        if E.slot is None:
            return
        got = yield from lib.discard_energy_from(E.g, E.p, E.slot, n, pred, E.ctx, E.card, units=True)
        E.data['discarded'] = len(got)
    return step


@pattern(r'Discard all Energy from this Pokémon')
def _(m):
    return lambda E: E.g.discard_energy(E.slot, list(E.slot.energy), E.ctx)


@pattern(rf"(?:If heads, )?[Dd]iscard (an|a Special|{NUMW}) Energy from your opponent's Active Pokémon")
def _(m):
    raw = m.group(1)
    special = 'Special' in raw
    n = 1 if raw in ('an', 'a Special') else num(raw)

    def step(E):
        t = E.opp_active()
        if t is None or E.g.effects_prevented(E.ctx, t):
            return
        yield from lib.discard_energy_from(E.g, E.p, t, n, (lambda e: e.d.special_energy) if special else None,
                                           None, E.card)
    return step


@pattern(r"For each heads, discard an Energy from your opponent's Active Pokémon")
def _(m):
    def step(E):
        t = E.opp_active()
        if t is None or E.g.effects_prevented(E.ctx, t):
            return
        yield from lib.discard_energy_from(E.g, E.p, t, E.data.get('heads_n', 0), None, None, E.card)
    return step


@pattern(rf'Move (an|all|{NUMW}) Energy from this Pokémon to {NUMW} of your Benched Pokémon')
def _(m):
    n = 99 if m.group(1) == 'all' else num(m.group(1))

    def step(E):
        if not E.me.bench:
            return
        if n >= 99:
            t = yield from E.g.choose_slot(E.p, E.me.bench, 'attach_target', 'Mover todas as Energias para', E.card)
            for e in list(E.slot.energy):
                E.slot.energy.remove(e)
                t.energy.append(e)
            return
        yield from lib.move_energy(E.g, E.p, lambda: [E.slot], lambda: E.me.bench, n, source=E.card, min_n=n)
    return step


@pattern(r'Put an Energy attached to this Pokémon into your hand')
def _(m):
    def step(E):
        if not E.slot.energy:
            return
        got = yield from E.g.choose_cards(E.p, E.slot.energy, 1, 1, 'pick', 'Energia para a mão', E.card)
        for e in got:
            E.slot.energy.remove(e)
            E.me.hand.append(e)
    return step


@pattern(r"(?:You may )?[Pp]ut (?:an|1) Energy attached to your opponent's Active Pokémon into their hand")
def _(m):
    def step(E):
        t = E.opp_active()
        if t is None or not t.energy or E.g.effects_prevented(E.ctx, t):
            return
        got = yield from E.g.choose_cards(E.p, t.energy, 1, 1, 'pick', 'Energia do oponente para a mão dele', E.card)
        for e in got:
            t.energy.remove(e)
            E.op.hand.append(e)
    return step


@pattern(rf'Attach (up to {NUMW}|a|an|{NUMW}) (.+?) cards? from your discard pile to (.+)')
def _(m):
    q = m.group(1)
    n = num(q.replace('up to ', '')) if q not in ('a', 'an') else 1
    pred = card_filter(m.group(4))
    dest = m.group(5)
    slots_fn, each_once = _attach_dest(dest)

    def step(E):
        yield from lib.attach_from_discard(E.g, E.p, pred, n, lambda: slots_fn(E), E.card, each_once=each_once)
    return step


@pattern(rf'Search your deck for (up to {NUMW}|a|an|{NUMW}) (.+?) cards? and attach (?:them|it) to (.+?)(?:\. Then, shuffle your deck)?')
def _(m):
    q = m.group(1)
    n = num(q.replace('up to ', '')) if q not in ('a', 'an') else 1
    pred = card_filter(m.group(4))
    slots_fn, each_once = _attach_dest(m.group(5))

    def step(E):
        yield from lib.search_attach(E.g, E.p, pred, n, lambda: slots_fn(E), E.card, each_once=each_once)
    return step


def _attach_dest(dest):
    dest = dest.strip().rstrip('.')
    each_once = False
    if dest in ('this Pokémon', 'it'):
        return (lambda E: [E.slot]), False
    if dest == 'your Active Pokémon':
        return (lambda E: [E.me.active] if E.me.active else []), False
    m = re.match(r'^your (Benched )?(.*?)Pokémon in any way you like$', dest)
    if m:
        bench = bool(m.group(1))
        f = slot_filter(m.group(2) + 'Pokémon')
        return (lambda E: [s for s in (E.me.bench if bench else E.me.in_play()) if f(E.g, s)]), False
    m = re.match(rf'^{NUMW} of your (Benched )?(.*?)Pokémon$', dest)
    if m:
        bench = bool(m.group(2))
        f = slot_filter(m.group(3) + 'Pokémon')
        return (lambda E: [s for s in (E.me.bench if bench else E.me.in_play()) if f(E.g, s)]), False
    m = re.match(r'^each of your (Benched )?(.*?)Pokémon$', dest)
    if m:
        bench = bool(m.group(1))
        f = slot_filter(m.group(2) + 'Pokémon')
        return (lambda E: [s for s in (E.me.bench if bench else E.me.in_play()) if f(E.g, s)]), True
    raise Unparsed(f'destino de energia: {dest}')


@pattern(rf'(?:You may )?[Aa]ttach (up to {NUMW}|a|an|any number of|{NUMW}) (.+?) cards? from your hand to (.+)')
def _(m):
    q = m.group(1)
    n = 99 if q == 'any number of' else (num(q.replace('up to ', '')) if q not in ('a', 'an') else 1)
    desc = m.group(4)
    if ' or ' in desc or ', ' in desc:
        pred = or_filter(desc.replace(' card', ''))
    else:
        pred = card_filter(desc)
    slots_fn, each_once = _attach_dest(m.group(5))

    def step(E):
        pl = E.me
        got = yield from E.g.choose_cards(E.p, [c for c in pl.hand if pred(c)], n, 0, 'attach_from_hand',
                                          'Energia da mão para ligar', E.card)
        for c in got:
            pl.hand.remove(c)
        before = {s.sid: len(s.energy) for s in pl.in_play()}
        yield from lib.attach_cards(E.g, E.p, got, lambda: slots_fn(E), E.card, each_once=each_once)
        E.data['did'] = bool(got)
        for s in pl.in_play():
            if len(s.energy) > before.get(s.sid, 0):
                E.data['that'] = s
    return step


@pattern(r'If you attached Energy to a Pokémon in this way, (.+)')
def _(m):
    inner = m.group(1)
    res = compile_sentence(inner[0].upper() + inner[1:])
    steps = [f for _, f in res]

    def step(E):
        if E.data.get('did'):
            for f in steps:
                yield from run(f(E))
    return step


@pattern(r'Heal (\d+) damage from that Pokémon')
def _(m):
    n = int(m.group(1))
    return lambda E: E.g.heal(E.data['that'], n) if E.data.get('that') else None


@pattern(rf'(?:You may )?[Ll]ook at the top (\d+) cards of your deck and attach any number of (.+?) cards you find there to (.+?)(?:\. (?:Shuffle the other cards (?:back into your deck|and put them on the bottom of your deck)))?')
def _(m):
    n = int(m.group(1))
    pred = card_filter(m.group(2))
    slots_fn, each_once = _attach_dest(m.group(3))
    to_bottom = 'bottom' in m.group(0)

    def step(E):
        pl = E.me
        top = pl.deck[:n]
        del pl.deck[:len(top)]
        pl.limbo.extend(top)
        got = yield from E.g.choose_cards(E.p, [c for c in top if pred(c)], len(top), 0, 'look',
                                          'Energias para ligar', E.card, key=lambda c: c.uid)
        for c in got:
            pl.limbo.remove(c)
        yield from lib.attach_cards(E.g, E.p, got, lambda: slots_fn(E), E.card, each_once=each_once)
        rest = [c for c in top if c not in got]
        for c in rest:
            pl.limbo.remove(c)
        E.g.rng.shuffle(rest)
        if to_bottom:
            pl.deck.extend(rest)
        else:
            pl.deck.extend(rest)
            E.g.shuffle(E.p)
    return step


@pattern(r'Shuffle the other cards and put them on the bottom of your deck')
def _(m):
    return None


@pattern(r"(?:You may )?[Ll]ook at the top (\d+) cards of (your|your opponent's) deck and put them back in any order")
def _(m):
    n = int(m.group(1))
    opp = m.group(2) != 'your'

    def step(E):
        from .trainers import reorder_top
        yield from reorder_top(E.g, E.opp if opp else E.p, n, E.card)
    return step


# --- busca / recuperação
@pattern(rf'(?:You may )?[Ss]earch your deck for (up to {NUMW}|a|an|{NUMW}|any number of) (.+?),? (?:reveal (?:them|it), )?and put (?:them|it) into your hand(?:\. Then, shuffle your deck)?')
def _(m):
    q = m.group(1)
    n = 99 if q == 'any number of' else (num(q.replace('up to ', '')) if q not in ('a', 'an') else 1)
    pred = or_filter(m.group(4))

    def step(E):
        yield from lib.search_to_hand(E.g, E.p, pred, n, E.card)
    return step


@pattern(rf'(?:You may )?[Ss]earch your deck for (up to {NUMW}|a|an|{NUMW}|any number of) (.+?) and put (?:them|it) onto your Bench(?:\. Then, shuffle your deck)?')
def _(m):
    q = m.group(1)
    n = 99 if q == 'any number of' else (num(q.replace('up to ', '')) if q not in ('a', 'an') else 1)
    desc = m.group(4)
    if re.search(r'Pokémon|Pokemon', desc):
        pred = or_filter(desc)
    else:   # nomes: "Grubbin", "Silcoon or a Cascoon"
        names = [x.strip() for x in re.split(r'\s+or\s+(?:an?\s+)?', desc)]
        pred = lambda c, names=names: c.d.kind == 'pokemon' and c.d.name in names

    def step(E):
        yield from lib.search_to_bench(E.g, E.p, pred, n, E.card)
    return step


@pattern(r'(?:You may )?[Ss]earch your deck for (?:a|up to \d+) cards? and put (?:it|them) into your hand(?:\. Then, shuffle your deck)?')
def _(m):
    n = int(re.search(r'up to (\d+)', m.group(0)).group(1)) if 'up to' in m.group(0) else 1
    return lambda E: lib.search_to_hand(E.g, E.p, lambda c: True, n, E.card)


@pattern(r'Then, shuffle your deck|Shuffle the other cards back into your deck')
def _(m):
    return None   # já embutido nas buscas


@pattern(rf'Put (up to {NUMW}|a|an|{NUMW}) (.+?) from your discard pile into your hand')
def _(m):
    q = m.group(1)
    n = num(q.replace('up to ', '')) if q not in ('a', 'an') else 1
    pred = or_filter(re.sub(r'^(in any combination of)\s+', '', m.group(4)))
    return lambda E: lib.recover(E.g, E.p, pred, n, 'hand', E.card)


@pattern(rf'Shuffle (up to {NUMW}|a|an|{NUMW}) (.+?) from your discard pile into your deck')
def _(m):
    q = m.group(1)
    n = num(q.replace('up to ', '')) if q not in ('a', 'an') else 1
    pred = or_filter(re.sub(r'^(in any combination of)\s+', '', m.group(4)))
    return lambda E: lib.recover(E.g, E.p, pred, n, 'deck', E.card)


@pattern(r'Search your deck for a card that evolves from this Pokémon and put it onto this Pokémon to evolve it(?:\. Then, shuffle your deck)?')
def _(m):
    def step(E):
        s = E.slot
        c = [x for x in E.me.deck if x.d.is_evolution and x.d.evolves_from == s.name]
        got = yield from E.g.choose_cards(E.p, c, 1, 0, 'search', 'Evoluir com', E.card)
        for x in got:
            E.me.deck.remove(x)
            yield from E.g.evolve(E.p, s, x, from_hand=False)
        E.g.shuffle(E.p)
    return step


# --- troca
@pattern(rf'(?:You may )?[Ss]witch this Pokémon with {NUMW} of your Benched Pokémon')
def _(m):
    optional = m.group(0).startswith('You may')

    def step(E):
        if not E.me.bench or not E.g.is_active(E.slot):
            return
        if optional and not (yield from E.g.yes_no(E.p, 'Trocar este Pokémon com um do Banco?', source=E.card)):
            return
        yield from lib.switch_own(E.g, E.p, E.card)
    return step


@pattern(r'Switch your Active Pokémon with 1 of your Benched Pokémon')
def _(m):
    return lambda E: lib.switch_own(E.g, E.p, E.card)


@pattern(r"Switch out your opponent's Active Pokémon to the Bench")
def _(m):
    def step(E):
        if E.ctx is not None and E.op.active is not None and E.g.effects_prevented(E.ctx, E.op.active):
            return
        yield from lib.opp_switches_out(E.g, E.p, E.card)
    return step


@pattern(rf"Switch in {NUMW} of your opponent's Benched Pokémon to the Active Spot", 'pre')
def _(m):
    def step(E):
        s = yield from lib.gust(E.g, E.p, source=E.card)
        if E.ctx is not None and s is not None:
            E.ctx.defender = s
        E.data['did'] = s is not None
    return step


@pattern(r'(?:You may )?[Dd]iscard a Stadium in play')
def _(m):
    optional = 'may' in m.group(0)

    def step(E):
        st = E.g.stadium
        if st is None:
            return
        if optional and not (yield from E.g.yes_no(E.p, f'Descartar {st.name}?', source=E.card)):
            return
        yield from E.g.discard_stadium()
    return step


@pattern(r"Before doing damage, discard all Pokémon Tools from your opponent's Active Pokémon", 'pre')
def _(m):
    def step(E):
        t = E.opp_active()
        if t is not None and t.tools and not E.g.effects_prevented(E.ctx, t):
            E.g.discard_cards(t.tools)
            t.tools = []
    return step


@pattern(r'Shuffle this Pokémon and all attached cards into your deck|You may shuffle this Pokémon and all attached cards into your deck')
def _(m):
    optional = 'may' in m.group(0)

    def step(E):
        if optional and not (yield from E.g.yes_no(E.p, 'Embaralhar este Pokémon no baralho?', source=E.card)):
            return
        E.g.remove_slot(E.slot, to='deck')
    return step


@pattern(r'Put this Pokémon and all attached cards into your hand')
def _(m):
    return lambda E: E.g.remove_slot(E.slot, to='hand')


# --- contadores de dano
@pattern(rf"Put (\d+) damage counters? on your opponent's Benched Pokémon in any way you like")
def _(m):
    n = int(m.group(1))
    return lambda E: lib.distribute_counters(E.g, E.p, n, lambda: E.op.bench, E.kind, E.ctx, E.card)


@pattern(rf"Put (\d+) damage counters? on your opponent's Pokémon in any way you like")
def _(m):
    n = int(m.group(1))
    return lambda E: lib.distribute_counters(E.g, E.p, n, lambda: E.op.in_play(), E.kind, E.ctx, E.card)


@pattern(rf"(?:Put|Place) (\d+) damage counters? on {NUMW} of your opponent's (Benched )?Pokémon")
def _(m):
    n, bench = int(m.group(1)), bool(m.group(3))

    def step(E):
        c = E.op.bench if bench else E.op.in_play()
        s = yield from E.g.choose_slot(E.p, c, 'counters', f'Colocar {n} contadores em', E.card)
        if s is not None:
            E.g.place_counters(s, n, E.kind, by=E.p, ctx=E.ctx)
    return step


@pattern(r"Put damage counters on your opponent's Active Pokémon until its remaining HP is (\d+)")
def _(m):
    n = int(m.group(1))

    def step(E):
        t = E.opp_active()
        if t is not None:
            left = E.g.hp_left(t)
            if left > n:
                E.g.place_counters(t, (left - n) // 10, E.kind, by=E.p, ctx=E.ctx)
    return step


@pattern(r"(?:Put|Place) (\d+) damage counters? on your opponent's Active Pokémon(?: for each (.+))?")
def _(m):
    n = int(m.group(1))
    cnt = count_expr(m.group(2)) if m.group(2) else (lambda E: 1)

    def step(E):
        t = E.opp_active()
        if t is not None:
            E.g.place_counters(t, n * cnt(E), E.kind, by=E.p, ctx=E.ctx)
    return step


@pattern(r"(?:Put|Place) (\d+) damage counters? on each of your opponent's (.*?)Pokémon")
def _(m):
    n = int(m.group(1))
    f = slot_filter((m.group(2) or '') + 'Pokémon')

    def step(E):
        for s in list(E.op.in_play()):
            if f(E.g, s):
                E.g.place_counters(s, n, E.kind, by=E.p, ctx=E.ctx)
    return step


@pattern(r'Then, discard that Stadium')
def _(m):
    def step(E):
        yield from E.g.discard_stadium()
    return step


@pattern(r'You may discard any amount of (Basic )?Energy from your Pokémon', 'pre')
def _(m):
    only_basic = bool(m.group(1))

    def step(E):
        pool = [(s, e) for s in E.me.in_play() for e in s.energy if (e.d.basic_energy or not only_basic)]
        where = {e.uid: s for s, e in pool}
        got = yield from E.g.choose_cards(E.p, [e for _, e in pool], len(pool), 0, 'discard_energy_any',
                                          'Energias a descartar', E.card, key=lambda e: (where[e.uid].sid, e.d.id),
                                          labeler=lambda e: f'{e.name} — {E.g.slot_label(where[e.uid])}')
        for e in got:
            E.g.discard_energy(where[e.uid], [e], E.ctx)
        E.data['discarded'] = len(got)
    step.est = lambda E, d: (E.data.update(discarded=sum(1 for s in E.me.in_play() for e in s.energy
                                                          if e.d.basic_energy or not only_basic)) or d)
    return step


@pattern(rf'(?:You may )?shuffle (\d+) Energy attached to this Pokémon into your deck', 'pre')
def _(m):
    n = int(m.group(1))
    optional = m.group(0).startswith('You may')

    def step(E):
        E.data['did'] = False
        s = E.slot
        if len(s.energy) < n:
            return
        if optional and not (yield from E.g.yes_no(E.p, f'Embaralhar {n} Energias no baralho?', source=E.card)):
            return
        got = yield from E.g.choose_cards(E.p, s.energy, n, n, 'pick', 'Energias para o baralho', E.card,
                                          key=lambda c: c.uid)
        for e in got:
            s.energy.remove(e)
            E.me.deck.append(e)
        E.g.shuffle(E.p)
        E.data['did'] = True
    return step


@pattern(r"This attack also does (\d+) damage to 1 of your opponent's Benched Pokémon")
def _(m):
    n = int(m.group(1))
    return lambda E: lib.bench_damage(E.g, E.ctx, 1, n, 'opp')


@pattern(rf'Put (up to {NUMW}|a|an|{NUMW}) (.+?) from your discard pile onto your Bench')
def _(m):
    q = m.group(1)
    n = num(q.replace('up to ', '')) if q not in ('a', 'an') else 1
    desc = m.group(4)
    if 'Pokémon' in desc:
        pred = or_filter(desc)
    else:
        names = [x.strip() for x in re.split(r'\s+or\s+|,\s*', desc)]
        pred = lambda c, names=names: c.d.kind == 'pokemon' and c.d.is_basic and c.d.name in names

    def step(E):
        k = min(n, E.g.bench_space(E.p))
        got = yield from E.g.choose_cards(E.p, [c for c in E.me.discard if pred(c) and c.d.is_basic], k, 0,
                                          'recover', 'Do descarte para o Banco', E.card)
        for c in got:
            E.me.discard.remove(c)
            yield from E.g.play_to_bench(E.p, c)
    return step


@pattern(r'Shuffle it and all attached cards into your deck')
def _(m):
    return lambda E: E.g.remove_slot(E.slot, to='deck')


@pattern(rf"You may (discard (\d+) ({TYPE_WORDS}|Basic)? ?Energy from this Pokémon|put an? ({TYPE_WORDS})? ?Energy attached to this Pokémon into your hand) and have this attack do (\d+) more damage", 'pre')
def _(m):
    discard = m.group(1).startswith('discard')
    k = int(m.group(2)) if discard else 1
    t = m.group(3) if discard else m.group(4)
    code = NAME_TO_TYPE.get(t) if t and t != 'Basic' else None
    bonus = int(m.group(5))

    def ok(e):
        if code:
            return e.d.provides == code or e.d.special_energy
        return e.d.basic_energy if t == 'Basic' else True

    def step(E):
        s = E.slot
        cands = [e for e in s.energy if ok(e)]
        if len(cands) < k:
            return
        if not (yield from E.g.yes_no(E.p, f'{"Descartar" if discard else "Devolver"} {k} Energia(s) para +{bonus} de dano?',
                                      source=E.card)):
            return
        got = yield from E.g.choose_cards(E.p, cands, k, k, 'pick', 'Energias', E.card, key=lambda c: c.uid)
        if discard:
            E.g.discard_energy(s, got, E.ctx)
        else:
            for e in got:
                s.energy.remove(e)
                E.me.hand.append(e)
        E.ctx.damage += bonus
    step.est = lambda E, d: d + bonus
    return step


@pattern(r"During your next turn, this Pokémon's (.+?) attack does (\d+) more damage")
def _(m):
    name, n = m.group(1), int(m.group(2))

    def step(E):
        s = E.slot
        E.g.add_effect(f'{name} +{n}', E.p, {'damage_out': lambda g, src, dmg, ctx, target, s=s:
                       dmg + n if ctx.attacker is s and ctx.attack.name == name else None},
                       target=s, duration='my_next_turn', while_active=True)
    return step


# --- efeitos com duração
@pattern(r"During your next turn, this Pokémon can't (?:attack|use attacks)")
def _(m):
    def step(E):
        s = E.slot
        E.g.add_effect('não pode atacar', E.p, {'can_attack': lambda g, src, slot, attack, s=s: False if slot is s else None},
                       target=s, duration='my_next_turn')
    return step


@pattern(r"During your next turn, this Pokémon can't use (.+)")
def _(m):
    name = m.group(1).strip()

    def step(E):
        s = E.slot
        E.g.add_effect(f'não pode usar {name}', E.p,
                       {'can_attack': lambda g, src, slot, attack, s=s: False if slot is s and attack.name == name else None},
                       target=s, duration='my_next_turn')
    return step


@pattern(r"During your next turn, this Pokémon can't retreat")
def _(m):
    def step(E):
        s = E.slot
        E.g.add_effect('não pode recuar', E.p, {'can_retreat': lambda g, src, slot, s=s: False if slot is s else None},
                       target=s, duration='my_next_turn')
    return step


@pattern(r"During your opponent's next turn, (?:the Defending Pokémon|that Pokémon) can't retreat")
def _(m):
    def step(E):
        t = E.opp_active()
        if t is None or E.g.effects_prevented(E.ctx, t):
            return
        E.g.add_effect('não pode recuar', E.p, {'can_retreat': lambda g, src, slot, t=t: False if slot is t else None},
                       target=t, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"During your opponent's next turn, (?:the Defending Pokémon|that Pokémon) can't (?:attack|use attacks)")
def _(m):
    def step(E):
        t = E.opp_active()
        if t is None or E.g.effects_prevented(E.ctx, t):
            return
        E.g.add_effect('não pode atacar', E.p, {'can_attack': lambda g, src, slot, attack, t=t: False if slot is t else None},
                       target=t, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"During your opponent's next turn, this Pokémon takes (\d+) less damage from attacks")
def _(m):
    n = int(m.group(1))

    def step(E):
        s = E.slot
        E.g.add_effect(f'-{n} de dano', E.p,
                       {'damage_in': lambda g, src, dmg, ctx, target, active, s=s: dmg - n if target is s else None},
                       target=s, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"(?:If heads, )?[Dd]uring your opponent's next turn, prevent all damage (?:from and effects of attacks done to this Pokémon|done to this Pokémon by attacks)(?: from (Basic|Basic non-Colorless|Evolution) Pokémon)?(?: if that damage is (\d+) or less)?", 'post')
def _(m):
    effects_too = 'effects' in m.group(0)
    who = m.group(1)
    cap = int(m.group(2)) if m.group(2) else None

    def applies(g, ctx):
        a = ctx.attacker
        if who == 'Basic':
            return a.d.stage == 0
        if who == 'Basic non-Colorless':
            return a.d.stage == 0 and not g.has_type(a, 'C')
        if who == 'Evolution':
            return a.d.stage > 0
        return True

    def step(E):
        s = E.slot
        hooks = {'damage_in': lambda g, src, dmg, ctx, target, active, s=s:
                 0 if target is s and ctx.player != s.owner and applies(g, ctx) and (cap is None or dmg <= cap) else None}
        if effects_too:
            hooks['prevent_attack_effects'] = lambda g, src, ctx, target, s=s: target is s
        E.g.add_effect('proteção', E.p, hooks, target=s, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"During your opponent's next turn, attacks used by the Defending Pokémon do (\d+) less damage")
def _(m):
    n = int(m.group(1))

    def step(E):
        t = E.opp_active()
        if t is None or E.g.effects_prevented(E.ctx, t):
            return
        E.g.add_effect(f'ataques -{n}', E.p,
                       {'damage_out': lambda g, src, dmg, ctx, target, t=t: dmg - n if ctx.attacker is t else None},
                       target=t, duration='opp_next_turn', while_active=True)
    return step


@pattern(r"During your next turn, attacks used by this Pokémon do (\d+) more damage to your opponent's Active Pokémon")
def _(m):
    n = int(m.group(1))

    def step(E):
        s = E.slot
        E.g.add_effect(f'ataques +{n}', E.p,
                       {'damage_out': lambda g, src, dmg, ctx, target, s=s: dmg + n if ctx.attacker is s else None},
                       target=s, duration='my_next_turn', while_active=True)
    return step


@pattern(r"During your next turn, the Defending Pokémon takes (\d+) more damage from attacks")
def _(m):
    n = int(m.group(1))

    def step(E):
        t = E.opp_active()
        if t is None or E.g.effects_prevented(E.ctx, t):
            return
        E.g.add_effect(f'+{n} de dano recebido', E.p,
                       {'damage_in': lambda g, src, dmg, ctx, target, active, t=t: dmg + n if target is t else None},
                       target=t, duration='my_next_turn', while_active=True)
    return step


@pattern(r"During your opponent's next turn, they can't play any Item cards from their hand")
def _(m):
    def step(E):
        o = E.opp
        E.g.add_effect('trava de Itens', E.p,
                       {'can_play': lambda g, src, player, card, o=o: False if player == o and card.d.is_item else None},
                       duration='opp_next_turn')
    return step


@pattern(r"During your opponent's next turn, if the Defending Pokémon tries to use an attack, your opponent flips a coin. If tails, that attack doesn't happen")
def _(m):
    def step(E):
        t = E.opp_active()
        if t is None or E.g.effects_prevented(E.ctx, t):
            return
        E.g.add_effect('ataque incerto', E.p, target=t, duration='opp_next_turn', while_active=True, smokescreen=True)
    return step


@pattern(r'If you go first, you can use this attack during your first turn', 'flag')
def _(m):
    return {'first_turn': True}


@pattern(r'You can use this attack only if you go second, and only during your first turn', 'flag')
def _(m):
    return {'can_use': lambda g, s: not g.players[s.owner].went_first and g.first_turn(s.owner)}


# ======================================================================== montagem
def _split(text):
    t = re.sub(r'\s*\([^)]*\)', '', text or '').strip()
    t = t.replace('Pokemon', 'Pokémon')
    parts = re.split(r'(?<=[.!])\s+', t)
    # junta "Flip a coin. If tails, that attack doesn't happen." etc. só quando necessário
    out = []
    for s in parts:
        s = s.strip()
        if s:
            out.append(s)
    return out


COND_PREFIX = [
    (re.compile(r'^If heads, (.+)$'), lambda E: E.data.get('heads')),
    (re.compile(r'^If tails, (.+)$'), lambda E: not E.data.get('heads')),
    (re.compile(r'^If both of them are heads, (.+)$'), lambda E: E.data.get('heads_n') == 2),
    (re.compile(r'^If you do, (.+)$'), lambda E: E.data.get('did', True)),
]


def compile_sentence(s):
    """→ lista de (fase, função) ou dict de flags. Lança Unparsed."""
    for rx, cond in COND_PREFIX:
        m = rx.match(s)
        if m:
            inner = m.group(1)
            inner = inner[0].upper() + inner[1:]
            res = compile_sentence(inner)
            if isinstance(res, dict):
                return res
            if 'this attack does nothing' in inner.lower():
                return res
            return [(ph, _guard(cond, f)) for ph, f in res]
    m = re.match(r'^If (.+?), (this attack does .+)$', s)
    if m:
        c = cond_expr(m.group(1))
        inner = m.group(2)
        res = compile_sentence(inner[0].upper() + inner[1:])
        return [(ph, _guard(c, f)) for ph, f in res]
    for rx, builder, phase in PATTERNS:
        m = rx.match(s)
        if m:
            r = builder(m)
            if phase == 'flag':
                return r
            if r is None:
                return []
            return [(phase, r)]
    m = re.match(r'^If (.+?), (.+)$', s)
    if m:
        c = cond_expr(m.group(1))
        inner = m.group(2)
        res = compile_sentence(inner[0].upper() + inner[1:])
        if isinstance(res, dict):
            return res
        return [(ph, _guard(c, f)) for ph, f in res]
    raise Unparsed(s)


def _guard(cond, f):
    def step(E):
        if cond(E):
            return (yield from run(f(E)))
    if hasattr(f, 'est'):
        step.est = lambda E, d: f.est(E, d) if cond(E) else d
    return step


class Program:
    def __init__(self):
        self.pre, self.post, self.flags, self.unparsed = [], [], {}, []

    @property
    def status(self):
        if not self.unparsed:
            return 'ok'
        return 'partial' if (self.pre or self.post or self.flags) else 'missing'


def compile_text(text) -> Program:
    prog = Program()
    parts = _split(text)
    i = 0
    while i < len(parts):
        s = parts[i]
        res = None
        try:
            res = compile_sentence(s)
            i += 1
        except Unparsed:
            # frases que só fazem sentido juntas ("...flips a coin. If tails, that attack doesn't happen.")
            for k in (2, 3):
                if i + k <= len(parts):
                    try:
                        res = compile_sentence(' '.join(parts[i:i + k]))
                        i += k
                        break
                    except Unparsed:
                        continue
            if res is None:
                prog.unparsed.append(s)
                i += 1
                continue
        if isinstance(res, dict):
            prog.flags.update(res)
            continue
        for ph, f in res:
            (prog.pre if ph == 'pre' else prog.post).append(f)
    return prog


def attack_impl_from_text(text) -> AttackImpl:
    prog = compile_text(text)
    pre, post = prog.pre, prog.post

    def run_pre(g, ctx):
        E = Exec(g, ctx.player, ctx=ctx)
        ctx.data['E'] = E
        for f in pre:
            yield from run(f(E))
            if ctx.no_damage:
                break

    def run_post(g, ctx):
        E = ctx.data.get('E') or Exec(g, ctx.player, ctx=ctx)
        for f in post:
            yield from run(f(E))

    def estimate(g, slot, target):
        E = Exec(g, slot.owner, slot=slot)
        from ..core import AttackCtx
        d = None
        for a in slot.d.attacks:
            if a.text == text:
                d = a.damage
        d = d or 0
        for f in pre:
            if hasattr(f, 'est'):
                try:
                    d = f.est(E, d)
                except Exception:
                    pass
        return max(0, int(d))

    fl = prog.flags
    im = AttackImpl(pre=run_pre if pre else None, post=run_post if post else None, estimate=estimate,
                    ignore_effects=fl.get('ignore_effects', False), ignore_weakness=fl.get('ignore_weakness', False),
                    ignore_resistance=fl.get('ignore_resistance', False), status=prog.status,
                    note='; '.join(prog.unparsed))
    if 'can_use' in fl:
        im.can_use = fl['can_use']
    if fl.get('first_turn'):
        im.first_turn = True
    return im


def steps_runner(prog, mode):
    """Executor de um programa compilado para Treinadores (mode='trainer') ou Habilidades ('ability')."""
    steps = prog.pre + prog.post

    def run_trainer(g, p, card):
        E = Exec(g, p, card=card)
        for f in steps:
            yield from run(f(E))

    def run_ability(g, p, slot):
        E = Exec(g, p, slot=slot)
        for f in steps:
            yield from run(f(E))
    return run_trainer if mode == 'trainer' else run_ability
