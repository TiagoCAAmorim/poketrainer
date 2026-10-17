"""Base de cartas: carrega ptcg/data/cards.json e liga as implementações de efeitos."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .core import AbilityDef, AttackDef, CardDef

DATA = Path(__file__).resolve().parent / 'data' / 'cards.json'
ERRATA = Path(__file__).resolve().parent / 'data' / 'errata.json'
_FOSSIL = re.compile(r'^Play this card as if it were a (\d+)-HP Basic (\w+) Pokémon')


def norm(s: str) -> str:
    s = s.replace('’', "'").replace('é', 'e').replace('É', 'E')
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return ' '.join(s.lower().split())


def parse_damage(s):
    s = (s or '').strip().replace('x', '×')
    m = re.match(r'^(\d+)\s*([+×\-]?)$', s)
    if not m:
        return 0, ''
    return int(m.group(1)), m.group(2)


class CardDB:
    def __init__(self, path=DATA):
        raw = json.load(open(path, encoding='utf-8'))
        self.sets = raw['sets']
        self.prints = raw['prints']
        self.cards: dict[str, CardDef] = {}
        self.by_name: dict[str, list[CardDef]] = {}
        errata = json.load(open(ERRATA, encoding='utf-8')) if ERRATA.exists() else {}
        for i, (cid, c) in enumerate(sorted(raw['cards'].items()), start=1):
            fix = errata.get(c['name'])
            if fix:
                c = dict(c)
                for a in c.get('abilities') or []:
                    if a['name'] in fix.get('abilities', {}):
                        a['text'] = fix['abilities'][a['name']]
                for a in c.get('attacks') or []:
                    if a['name'] in fix.get('attacks', {}):
                        a['text'] = fix['attacks'][a['name']]
                if 'text' in fix:
                    c['text'] = fix['text']
            d = self._build(c)
            d.idx = i
            self.cards[cid] = d
            self.by_name.setdefault(norm(d.name), []).append(d)
        for t, n in (('G', 'Grass'), ('R', 'Fire'), ('W', 'Water'), ('L', 'Lightning'), ('P', 'Psychic'),
                     ('F', 'Fighting'), ('D', 'Darkness'), ('M', 'Metal')):
            ds = self.by_name.get(norm(f'Basic {n} Energy'))
            if ds:
                self.by_name.setdefault(norm(f'{n} Energy'), ds)
        # nomes em português (lista exportada do TCG Live em pt-BR, buscas na biblioteca)
        self.by_name_pt: dict[str, list[CardDef]] = {}
        ptp = Path(__file__).resolve().parent / 'data' / 'cards_pt.json'
        pt = json.load(open(ptp, encoding='utf-8')) if ptp.exists() else {}
        for d in self.cards.values():
            nm = (pt.get(d.id) or {}).get('name') or d.name_pt
            if nm and d not in self.by_name_pt.get(norm(nm), []):
                self.by_name_pt.setdefault(norm(nm), []).append(d)
        for t, en, ptn in (('G', 'Grass', 'Planta'), ('R', 'Fire', 'Fogo'), ('W', 'Water', 'Água'),
                           ('L', 'Lightning', 'Elétrico'), ('P', 'Psychic', 'Psíquico'), ('F', 'Fighting', 'Lutador'),
                           ('D', 'Darkness', 'Escuridão'), ('M', 'Metal', 'Metal')):
            ds = self.by_name.get(norm(f'Basic {en} Energy'))
            if ds:
                for alias in (f'Energia de {ptn} Básica', f'Energia Básica de {ptn}', f'Energia de {ptn}',
                              f'Energia {ptn} Básica', f'Energia {ptn}'):
                    self.by_name_pt.setdefault(norm(alias), ds)
        from .effects import bind_all
        bind_all(self)

    @staticmethod
    def _build(c) -> CardDef:
        d = CardDef(id=c['id'], name=c['name'], kind=c['kind'], name_pt=c.get('name_pt'),
                    subtype=c.get('subtype'), stage=c.get('stage', 0), evolves_from=c.get('evolves_from'),
                    hp=c.get('hp', 0), types=list(c.get('types') or []), weakness=c.get('weakness'),
                    resistance=c.get('resistance'), resistance_value=c.get('resistance_value') or 30,
                    retreat=c.get('retreat', 0), tags=set(c.get('tags') or []), text=c.get('text') or '',
                    provides=c.get('provides'), prints=c.get('prints') or [])
        for a in c.get('attacks') or []:
            dmg, suf = parse_damage(a.get('damage'))
            d.attacks.append(AttackDef(a['name'], list(a.get('cost') or []), dmg, suf, a.get('text') or '',
                                       owner_name=d.name))
        for a in c.get('abilities') or []:
            d.abilities.append(AbilityDef(a['name'], a.get('text') or ''))
        m = _FOSSIL.match(d.text or '')
        if d.kind == 'trainer' and m:
            d.as_pokemon = True
            d.hp = int(m.group(1))
            d.types = ['C']
            d.tags.add('fossil')
        return d

    # ------------------------------------------------------------ busca
    def get(self, cid) -> CardDef:
        return self.cards[cid]

    def named(self, name) -> list[CardDef]:
        k = norm(name)
        return self.by_name.get(k) or self.by_name_pt.get(k, [])

    def resolve(self, name: str = None, set_code: str = None, number: str = None) -> CardDef:
        """Resolve uma entrada de lista ('Charizard ex', 'OBF', '125') para a carta legal."""
        if set_code and number:
            num = str(number).lstrip('0') or '0'
            for code in (set_code.upper(), set_code.upper().replace('PR-', '')):
                p = self.prints.get(f'{code}-{num}')
                if p:
                    if p.get('id'):
                        return self.cards[p['id']]
                    name = name or p['name']
                    break
        if not name:
            raise KeyError(f'Impressão desconhecida: {set_code} {number}')
        ds = self.named(name)
        if not ds:
            raise KeyError(f'Carta não encontrada (ou fora da rotação H/I/J): {name!r}'
                           + (f' {set_code} {number}' if set_code else ''))
        return ds[0]


_DB: CardDB | None = None


def db() -> CardDB:
    global _DB
    if _DB is None:
        _DB = CardDB()
    return _DB


def vocab_size() -> int:
    return len(db().cards) + 1
