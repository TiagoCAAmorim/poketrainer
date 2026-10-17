"""Listas de deck: leitura (formato TCG Live / Limitless), validação, escrita e geração aleatória."""
from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .carddb import db

DECK_DIR = Path(__file__).resolve().parent.parent / 'decks'
_HEADER = re.compile(r'^(pok[eé]mon|trainer|treinador|energy|energia|total cards)\b.*?(:|\(\d+\))', re.I)
_LINE = re.compile(r'^(\d+)\s*x?\s+(.+?)(?:\s+(PR-[A-Z]{2}|[A-Z0-9]{2,4})\s+(\d+[a-z]?))?\s*$')


@dataclass
class Deck:
    name: str
    cards: list                       # ids de carta (60)
    meta: dict = field(default_factory=dict)

    def counts(self) -> Counter:
        return Counter(self.cards)

    def defs(self):
        D = db()
        return [D.get(c) for c in self.cards]


def parse_decklist(text: str, name: str = 'deck'):
    """Aceita '3 Dragapult ex TWM 130', '4 Buddy-Buddy Poffin TEF 144', '8 Basic Fire Energy SVE 2',
    '1 Pecharunt PR-SV 149' ou só '4 Ultra Ball'. Retorna (Deck, erros)."""
    D = db()
    cards, errors, meta = [], [], {}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('#'):
            m = re.match(r'#\s*(\w+)\s*:\s*(.+)$', line)
            if m:
                meta[m.group(1).lower()] = m.group(2).strip()
            continue
        if not line or _HEADER.match(line):
            continue
        m = _LINE.match(line)
        if not m:
            errors.append(f'Linha não reconhecida: {raw!r}')
            continue
        n, nm, code, number = int(m.group(1)), m.group(2).strip(), m.group(3), m.group(4)
        try:
            d = D.resolve(nm, code, number)
        except KeyError:
            try:   # o "código" pode fazer parte do nome (ex.: "Technical Machine: Fluorite")
                d = D.resolve(f'{nm} {code} {number}'.strip() if code else nm)
            except KeyError as e:
                errors.append(str(e))
                continue
        cards += [d.id] * n
    return Deck(name, cards, meta), errors


def validate(card_ids) -> list:
    D = db()
    errs = []
    defs = [D.get(c) for c in card_ids]
    if len(defs) != 60:
        errs.append(f'O deck tem {len(defs)} cartas (precisa de 60)')
    names = Counter(d.name for d in defs)
    for nm, n in names.items():
        d = D.named(nm)[0]
        if not d.basic_energy and n > 4:
            errs.append(f'{nm}: {n} cópias (máximo 4)')
    if not any(d.is_basic for d in defs):
        errs.append('Nenhum Pokémon Básico')
    ace = sum(1 for d in defs if d.ace_spec)
    if ace > 1:
        errs.append(f'{ace} cartas ACE SPEC (máximo 1)')
    return errs


def support_report(card_ids):
    """Cartas do deck cujo efeito ainda não está 100% implementado."""
    D = db()
    out = []
    for cid, n in Counter(card_ids).items():
        d = D.get(cid)
        if d.status != 'ok':
            out.append((d, n, d.status))
    return out


def load_deck(path_or_name, strict=True) -> Deck:
    p = Path(path_or_name)
    if not p.exists():
        for cand in (DECK_DIR / path_or_name, DECK_DIR / f'{path_or_name}.txt'):
            if cand.exists():
                p = cand
                break
        else:
            hits = list(DECK_DIR.rglob(f'{path_or_name}.txt'))
            if hits:
                p = hits[0]
    text = p.read_text(encoding='utf-8')
    deck, errors = parse_decklist(text, p.stem)
    errors += validate(deck.cards)
    if errors and strict:
        raise ValueError(f'Deck {p.name} inválido:\n  ' + '\n  '.join(errors))
    deck.meta['errors'] = errors
    deck.meta['path'] = str(p)
    return deck


def list_decks(sub=None) -> list:
    base = DECK_DIR / sub if sub else DECK_DIR
    return sorted(str(p.relative_to(DECK_DIR).with_suffix('')) for p in base.rglob('*.txt')
                  if not any(part.startswith('_') for part in p.relative_to(DECK_DIR).parts))


def deck_to_text(card_ids, meta=None) -> str:
    D = db()
    c = Counter(card_ids)
    groups = {'pokemon': [], 'trainer': [], 'energy': []}
    for cid, n in c.items():
        groups[D.get(cid).kind].append((D.get(cid), n))
    out = [f'# {k}: {v}' for k, v in (meta or {}).items() if isinstance(v, (str, int, float))]
    for title, key in (('Pokémon', 'pokemon'), ('Trainer', 'trainer'), ('Energy', 'energy')):
        items = sorted(groups[key], key=lambda x: (-x[1], x[0].name))
        out.append(f'{title}: {sum(n for _, n in items)}')
        for d, n in items:
            pr = d.prints[0] if d.prints else d.id
            code, num = pr.rsplit('-', 1)
            out.append(f'{n} {d.name} {code} {num}')
        out.append('')
    return '\n'.join(out)


def random_deck(rng: random.Random, statuses=('ok', 'partial'), lines=2):
    """Gera um deck legal aleatório (linhas de evolução + treinadores + energias) para testes de estresse."""
    D = db()
    pool = [d for d in D.cards.values() if d.status in statuses]
    basics = [d for d in pool if d.is_basic]
    evos = {}
    for d in pool:
        if d.is_evolution:
            evos.setdefault(d.evolves_from, []).append(d)
    trainers = [d for d in pool if d.kind == 'trainer']
    specials = [d for d in pool if d.special_energy]
    energies = [d for d in D.cards.values() if d.basic_energy]
    deck = []
    types = set()
    for _ in range(lines):
        b = rng.choice(basics)
        deck += [b] * rng.randint(2, 4)
        types |= set(b.types)
        s1 = evos.get(b.name)
        if s1:
            x = rng.choice(s1)
            deck += [x] * rng.randint(1, 3)
            types |= set(x.types)
            s2 = evos.get(x.name)
            if s2:
                y = rng.choice(s2)
                deck += [y] * rng.randint(1, 3)
                types |= set(y.types)
                deck += [d for d in pool if d.name == 'Rare Candy'][:1] * 3
    for _ in range(rng.randint(2, 5)):
        deck.append(rng.choice(basics))
    ace_used = False
    while len(deck) < 48:
        t = rng.choice(trainers + specials * 0)
        if t.ace_spec:
            if ace_used:
                continue
            ace_used = True
        if sum(1 for x in deck if x.name == t.name) >= 4:
            continue
        k = 1 if t.ace_spec else min(rng.randint(1, 3), 4 - sum(1 for x in deck if x.name == t.name))
        deck += [t] * k
    deck = deck[:50]
    for _ in range(rng.randint(0, 2) if specials else 0):
        sp = rng.choice(specials)
        if sp.ace_spec and ace_used:
            continue
        if sp.ace_spec:
            ace_used = True
        deck.append(sp)
    tcodes = [t for t in types if t in 'GRWLPFDM'] or ['C']
    while len(deck) < 60:
        t = rng.choice(tcodes)
        cand = [e for e in energies if e.provides == t] or energies
        deck.append(rng.choice(cand))
    deck = deck[:60]
    names = Counter(d.name for d in deck)
    fixed = []
    seen = Counter()
    ace = 0
    for d in deck:
        if not d.basic_energy and seen[d.name] >= 4:
            continue
        if d.ace_spec:
            if ace:
                continue
            ace += 1
        seen[d.name] += 1
        fixed.append(d)
    while len(fixed) < 60:
        fixed.append(rng.choice(energies))
    ids = [d.id for d in fixed]
    assert not validate(ids), validate(ids)
    return ids
