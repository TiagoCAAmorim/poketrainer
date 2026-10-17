"""Registro de efeitos de cartas.

Ordem de resolução de cada carta:
  1. implementação escrita à mão (módulos trainers/tools/stadiums/energies/abilities/attacks)
  2. compilação automática do texto oficial (compiler.py)
Ataques sem texto são só dano e não precisam de implementação.
"""
from __future__ import annotations

from ..core import AbilityImpl, AttackImpl, TrainerImpl

TRAINERS: dict = {}     # nome normalizado -> TrainerImpl
ABILITIES: dict = {}    # nome normalizado da habilidade -> fábrica f(card_def, ability_def) -> AbilityImpl
ATTACKS: dict = {}      # (carta, ataque) normalizados -> fábrica f(card_def, attack_def) -> AttackImpl
ATTACKS_TEXT: dict = {} # texto exato -> fábrica


def _n(s):
    from ..carddb import norm
    return norm(s)


def trainer(name, **kw):
    """@trainer('Ultra Ball', can_play=...) sobre a função run(g, p, card)."""
    def deco(fn):
        TRAINERS[_n(name)] = TrainerImpl(run=fn, **kw)
        return fn
    return deco


def register_trainer(name, impl: TrainerImpl):
    TRAINERS[_n(name)] = impl
    return impl


def ability(name):
    """@ability('Teal Dance') sobre uma fábrica f(card_def, ability_def) -> AbilityImpl."""
    def deco(fn):
        ABILITIES[_n(name)] = fn
        return fn
    return deco


def attack(card=None, name=None, text=None):
    """@attack(card, name) ou @attack(text=...) sobre uma fábrica f(card_def, attack_def) -> AttackImpl."""
    def deco(fn):
        if text is not None:
            ATTACKS_TEXT[text] = fn
        else:
            ATTACKS[(_n(card), _n(name))] = fn
        return fn
    return deco


_LOADED = False


def _load_modules():
    global _LOADED
    if _LOADED:
        return
    from . import trainers, tools, stadiums, energies, abilities, attacks  # noqa: F401
    _LOADED = True


def bind_all(db):
    _load_modules()
    from .compiler import attack_impl_from_text, compile_text, steps_runner
    from .abilities import compile_ability
    for d in db.cards.values():
        if d.kind in ('trainer', 'energy') and not d.basic_energy:
            impl = TRAINERS.get(_n(d.name))
            if impl is None and d.kind == 'trainer' and d.subtype in ('item', 'supporter') and not d.as_pokemon:
                prog = compile_text(d.text)
                if not prog.unparsed and (prog.pre or prog.post):
                    impl = TrainerImpl(run=steps_runner(prog, 'trainer'), status='ok', note='compilado')
                else:
                    impl = TrainerImpl(run=steps_runner(prog, 'trainer'), status=prog.status,
                                       note='; '.join(prog.unparsed))
            if impl is None and d.as_pokemon:
                impl = TrainerImpl(status='ok', note='fóssil')
            d.impl = impl
        for ab in d.abilities:
            f = ABILITIES.get(_n(ab.name))
            impl = None
            if f is not None:
                try:
                    impl = f(d, ab)
                except Exception as e:   # fábrica não cobre esta versão do texto
                    impl = None
            ab.impl = impl if impl is not None else compile_ability(d, ab)
        for atk in d.attacks:
            f = ATTACKS.get((_n(d.name), _n(atk.name))) or ATTACKS_TEXT.get(atk.text)
            if f is not None:
                atk.impl = f(d, atk)
            elif atk.text:
                atk.impl = attack_impl_from_text(atk.text)
            else:
                atk.impl = None


def coverage(db):
    """Resumo de cobertura: {'ok': n, 'partial': n, 'missing': n} e listas por carta."""
    out = {'ok': [], 'partial': [], 'missing': []}
    for d in db.cards.values():
        out[d.status].append(d)
    return out
