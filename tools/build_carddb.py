"""Gera ptcg/data/cards.json com todas as cartas das séries Scarlet & Violet e Mega Evolution.

Fontes (repositórios abertos no GitHub):
  * PokemonTCG/pokemon-tcg-data  — dados principais (subtipos Tera/Ancient/Future/ACE SPEC, códigos)
  * tcgdex/cards-database        — nomes em português e sets que faltam na primeira fonte (MEP, MEE)

Uso:
    python tools/build_carddb.py                      # clona as fontes em .cache/ e gera o JSON
    python tools/build_carddb.py --ptcgdata DIR --tcgdex DIR

Formato de saída:
    cards:  {id: carta funcional}      (id = primeira impressão, ex. "TWM-130")
    prints: {"SET-NUM": {"name", "id"}} toda impressão SV/ME; id = carta legal equivalente ou null
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'ptcg' / 'data' / 'cards.json'
CACHE = ROOT / '.cache'

TYPE = {'Grass': 'G', 'Fire': 'R', 'Water': 'W', 'Lightning': 'L', 'Psychic': 'P', 'Fighting': 'F',
        'Darkness': 'D', 'Metal': 'M', 'Dragon': 'N', 'Colorless': 'C', 'Fairy': 'Y'}
SERIES = ('Scarlet & Violet', 'Mega Evolution')
LEGAL_MARKS = {'H', 'I', 'J'}
# códigos usados pelo TCG Live / Limitless que diferem do pokemontcg.io
CODE_ALIASES = {'PR-SV': ['SVP'], 'PR-ME': ['MEP']}


def git_clone(url, dest, sparse=None):
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ['git', 'clone', '--depth', '1']
    if sparse:
        cmd += ['--filter=blob:none', '--sparse']
    subprocess.check_call(cmd + [url, str(dest)])
    if sparse:
        subprocess.check_call(['git', '-C', str(dest), 'sparse-checkout', 'set'] + sparse)
    return dest


# ---------------------------------------------------------------- parser de literais JS (TCGdex)
class _JS:
    """Lê o objeto literal `const card: Card = {...}` dos arquivos .ts do TCGdex."""

    def __init__(self, s):
        self.s, self.i = s, 0

    def ws(self):
        s = self.s
        while self.i < len(s):
            if s[self.i].isspace():
                self.i += 1
            elif s.startswith('//', self.i):
                self.i = s.find('\n', self.i) if s.find('\n', self.i) >= 0 else len(s)
            elif s.startswith('/*', self.i):
                self.i = s.find('*/', self.i) + 2
            else:
                break

    def value(self):
        self.ws()
        c = self.s[self.i]
        if c == '{':
            return self.obj()
        if c == '[':
            return self.arr()
        if c in '"\'`':
            return self.string()
        m = re.compile(r'-?\d+(\.\d+)?').match(self.s, self.i)
        if m:
            self.i = m.end()
            return float(m.group()) if m.group(1) else int(m.group())
        m = re.compile(r'[A-Za-z_$][\w$.]*').match(self.s, self.i)
        self.i = m.end()
        return {'true': True, 'false': False, 'null': None, 'undefined': None}.get(m.group(), m.group())

    def string(self):
        q = self.s[self.i]
        self.i += 1
        out = []
        while self.s[self.i] != q:
            if self.s[self.i] == '\\':
                self.i += 1
                out.append({'n': '\n', 't': '\t'}.get(self.s[self.i], self.s[self.i]))
            else:
                out.append(self.s[self.i])
            self.i += 1
        self.i += 1
        return ''.join(out)

    def obj(self):
        self.i += 1
        out = {}
        while True:
            self.ws()
            if self.s[self.i] == '}':
                self.i += 1
                return out
            if self.s[self.i] in '"\'':
                k = self.string()
            else:
                m = re.compile(r'[\w$-]+').match(self.s, self.i)
                k, self.i = m.group(), m.end()
            self.ws()
            if self.s[self.i] == ':':
                self.i += 1
                out[k] = self.value()
            else:
                out[k] = k  # shorthand
            self.ws()
            if self.s[self.i] == ',':
                self.i += 1

    def arr(self):
        self.i += 1
        out = []
        while True:
            self.ws()
            if self.s[self.i] == ']':
                self.i += 1
                return out
            out.append(self.value())
            self.ws()
            if self.s[self.i] == ',':
                self.i += 1


def parse_ts_object(path):
    txt = Path(path).read_text(encoding='utf-8')
    m = re.search(r'(?:const|let)\s+\w+\s*(?::\s*\w+)?\s*=\s*', txt)
    p = _JS(txt)
    p.i = m.end()
    return p.value()


def load_tcgdex(root: Path):
    """Retorna {(CODE, NUM): carta_tcgdex} e {set_code: info} para as séries SV/ME."""
    cards, sets = {}, {}
    for serie in SERIES:
        sdir = root / 'data' / serie
        if not sdir.exists():
            continue
        for set_ts in sorted(sdir.glob('*.ts')):
            info = parse_ts_object(set_ts)
            code = (info.get('abbreviations') or {}).get('official') or info.get('id')
            if code in sets and str(info.get('id', '')).endswith('-c'):   # "30th Classic Collection" usa a mesma sigla 30C da "30th Celebration"
                code += 'C'   # (mesma convenção do ramo pokemontcg.io em main); sem isto, os nºs 1–30 sobrescreviam os da 30C
            sets[code] = {'id': info.get('id'), 'name': info['name'].get('en'), 'date': info.get('releaseDate'),
                          'serie': serie}
            cdir = sdir / set_ts.stem
            if not cdir.is_dir():
                continue
            for f in cdir.glob('*.ts'):
                try:
                    c = parse_ts_object(f)
                except Exception as e:  # arquivo fora do padrão
                    print(f'  aviso: não li {f}: {e}', file=sys.stderr)
                    continue
                c['_number'] = f.stem.lstrip('0') or '0'
                cards[(code, c['_number'])] = c
    return cards, sets


def _l(d, lang='en'):
    if isinstance(d, dict):
        return d.get(lang) or d.get('en')
    return d


def tcgdex_to_common(c, code):
    """Converte uma carta TCGdex para o mesmo formato da pokemontcg.io."""
    cat = {'Pokemon': 'Pokémon', 'Trainer': 'Trainer', 'Energy': 'Energy'}[c['category']]
    subtypes = []
    if cat == 'Pokémon':
        subtypes.append({'Basic': 'Basic', 'Stage1': 'Stage 1', 'Stage2': 'Stage 2'}.get(c.get('stage'), 'Basic'))
        if c.get('suffix') == 'ex':
            subtypes.append('ex')
        if _l(c['name']).startswith('Mega '):
            subtypes.append('MEGA')
    elif cat == 'Trainer':
        subtypes.append({'Tool': 'Pokémon Tool'}.get(c.get('trainerType'), c.get('trainerType') or 'Item'))
        if c.get('rarity') == 'ACE SPEC Rare':
            subtypes.append('ACE SPEC')
    else:
        subtypes.append('Basic' if c.get('energyType') == 'Normal' else 'Special')
    out = {'name': _l(c['name']), 'supertype': cat, 'subtypes': subtypes, 'number': c['_number'],
           'regulationMark': c.get('regulationMark'), 'set_code': code}
    if c.get('hp'):
        out['hp'] = str(c['hp'])
    if c.get('types'):
        out['types'] = c['types']
    if c.get('evolveFrom'):
        out['evolvesFrom'] = _l(c['evolveFrom'])
    if c.get('attacks'):
        out['attacks'] = [{'name': _l(a['name']), 'cost': a.get('cost') or [], 'damage': str(a.get('damage') or ''),
                           'text': _l(a.get('effect')) or ''} for a in c['attacks']]
    if c.get('abilities'):
        out['abilities'] = [{'name': _l(a['name']), 'text': _l(a['effect']), 'type': a.get('type', 'Ability')}
                            for a in c['abilities']]
    if c.get('weaknesses'):
        out['weaknesses'] = c['weaknesses']
    if c.get('resistances'):
        out['resistances'] = c['resistances']
    if c.get('retreat') is not None:
        out['convertedRetreatCost'] = c['retreat']
    if c.get('effect'):
        out['rules'] = [_l(c['effect'])]
    return out


# ---------------------------------------------------------------- normalização
def norm_card(x, code):
    st = x['supertype']
    sub = set(x.get('subtypes') or [])
    kind = {'Pokémon': 'pokemon', 'Trainer': 'trainer', 'Energy': 'energy'}[st]
    c = {'name': x['name'], 'kind': kind, 'regulation': x.get('regulationMark'), 'tags': []}
    if kind == 'pokemon':
        c['stage'] = 2 if 'Stage 2' in sub else 1 if 'Stage 1' in sub else 0
        c['hp'] = int(re.sub(r'\D', '', str(x.get('hp') or 0)) or 0)
        c['types'] = [TYPE[t] for t in x.get('types') or []]
        c['evolves_from'] = x.get('evolvesFrom')
        w = (x.get('weaknesses') or [None])[0]
        r = (x.get('resistances') or [None])[0]
        c['weakness'] = TYPE[w['type']] if w else None
        c['resistance'] = TYPE[r['type']] if r else None
        c['resistance_value'] = int(re.sub(r'[^\d]', '', r.get('value') or '30') or 30) if r else 0
        c['retreat'] = int(x.get('convertedRetreatCost') or len(x.get('retreatCost') or []))
        c['attacks'] = [{'name': a['name'], 'cost': [TYPE[t] for t in a.get('cost') or [] if t in TYPE],
                         'damage': str(a.get('damage') or ''), 'text': a.get('text') or ''}
                        for a in x.get('attacks') or []]
        c['abilities'] = [{'name': a['name'], 'text': a['text'], 'type': a.get('type', 'Ability')}
                          for a in x.get('abilities') or []]
        for t, tag in (('ex', 'ex'), ('Tera', 'tera'), ('Ancient', 'ancient'), ('Future', 'future'),
                       ('MEGA', 'mega')):
            if t in sub:
                c['tags'].append(tag)
        if x['name'].startswith('Mega ') and 'mega' not in c['tags']:
            c['tags'].append('mega')
    elif kind == 'trainer':
        tt = 'item'
        for t, v in (('Supporter', 'supporter'), ('Stadium', 'stadium'), ('Pokémon Tool', 'tool'),
                     ('Item', 'item')):
            if t in sub:
                tt = v
                break
        c['subtype'] = tt
        rules = [r for r in x.get('rules') or [] if not r.startswith('You may play only 1')
                 and not r.startswith('You may play any number of Item') and 'ACE SPEC' not in r
                 and not r.startswith('You may attach any number of Pokémon Tools')
                 and not r.startswith('This card stays in play when you play it')
                 and not r.startswith('Attach a Pokémon Tool to 1 of your Pokémon that doesn')]
        c['text'] = ' '.join(rules).strip()
        for t, tag in (('ACE SPEC', 'ace_spec'), ('Ancient', 'ancient'), ('Future', 'future')):
            if t in sub:
                c['tags'].append(tag)
        if x['name'].startswith('Technical Machine'):
            c['tags'].append('technical_machine')
    else:
        basic = 'Basic' in sub or x['name'].startswith('Basic ')
        c['subtype'] = 'basic' if basic else 'special'
        c['text'] = ' '.join(x.get('rules') or []).strip()
        if basic:
            m = re.match(r'(?:Basic )?(\w+) Energy', x['name'])
            c['provides'] = TYPE.get(m.group(1)) if m else None
            c['name'] = f'Basic {m.group(1)} Energy' if m else x['name']
            c['text'] = ''
        if 'ACE SPEC' in sub:
            c['tags'].append('ace_spec')
    return c


_SYM = {'G': 'Grass', 'R': 'Fire', 'W': 'Water', 'L': 'Lightning', 'P': 'Psychic', 'F': 'Fighting',
        'D': 'Darkness', 'M': 'Metal', 'N': 'Dragon', 'C': 'Colorless', 'Y': 'Fairy'}


def clean_text(t):
    """Normaliza textos das duas fontes: {G} → Grass, aspas tipográficas, espaços."""
    if not t:
        return t
    t = re.sub(r'\{([GRWLPFDMNCY])\}', lambda m: _SYM[m.group(1)], t)
    t = t.replace('’', "'").replace('“', '"').replace('”', '"').replace('\u00a0', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def clean_card(c):
    c['name'] = c['name'].replace('’', "'")
    if c.get('evolves_from'):
        c['evolves_from'] = c['evolves_from'].replace('’', "'")
    for a in c.get('attacks', []) + c.get('abilities', []):
        a['text'] = clean_text(a['text'])
        a['name'] = a['name'].replace('’', "'")
    if 'text' in c:
        c['text'] = clean_text(c['text'])
    return c


def functional_key(c):
    return json.dumps({k: c.get(k) for k in ('name', 'kind', 'hp', 'types', 'attacks', 'abilities', 'text',
                                             'subtype', 'stage', 'evolves_from', 'retreat', 'weakness')},
                      sort_keys=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ptcgdata', default=None)
    ap.add_argument('--tcgdex', default=None)
    ap.add_argument('--out', default=str(OUT))
    ap.add_argument('--marks', default=','.join(sorted(LEGAL_MARKS)),
                    help='marcas de regulação a incluir (padrão H,I,J; a página estática usa G,H,I,J p/ decks da temporada)')
    a = ap.parse_args()
    marks = set(a.marks.upper().split(','))
    pdir = Path(a.ptcgdata) if a.ptcgdata else git_clone('https://github.com/PokemonTCG/pokemon-tcg-data',
                                                         CACHE / 'pokemon-tcg-data')
    tdir = Path(a.tcgdex) if a.tcgdex else git_clone('https://github.com/tcgdex/cards-database', CACHE / 'tcgdex',
                                                     sparse=['data/Scarlet & Violet', 'data/Mega Evolution'])
    print('Lendo TCGdex…')
    tcg_cards, tcg_sets = load_tcgdex(tdir)
    print(f'  {len(tcg_cards)} impressões, {len(tcg_sets)} sets')

    raw = []  # (code, number, card_common, release)
    sets_meta = {}
    seen_codes = set()
    for s in json.load(open(pdir / 'sets' / 'en.json', encoding='utf-8')):
        if s['series'] not in SERIES:
            continue
        code = s.get('ptcgoCode') or s['id'].upper()
        f = pdir / 'cards' / 'en' / f'{s["id"]}.json'
        if not f.exists():
            continue
        if s['id'].endswith('c') and code in seen_codes:   # coleção clássica: mantém separada
            code = code + 'C'
        seen_codes.add(code)
        sets_meta[code] = {'name': s['name'], 'date': s['releaseDate'].replace('/', '-'), 'id': s['id']}
        for x in json.load(open(f, encoding='utf-8')):
            raw.append((code, x['number'], x, sets_meta[code]['date']))
    have = {c for c in sets_meta}
    for code, info in tcg_sets.items():            # sets ausentes na pokemontcg.io (ex.: MEP, MEE)
        alias = {'MEP': 'PR-ME'}.get(code, code)
        if code in have or alias in have or code in ('SVP',):
            continue
        sets_meta[alias] = {'name': info['name'], 'date': info['date'], 'id': info['id']}
        for (c2, num), tc in tcg_cards.items():
            if c2 == code:
                raw.append((alias, num, tcgdex_to_common(tc, alias), info['date']))
        print(f'  + set {alias} ({info["name"]}) vindo do TCGdex')

    # nomes em português via TCGdex (mesmo código + número)
    tcg_by_code = {}
    for (code, num), tc in tcg_cards.items():
        tcg_by_code[(code, num)] = tc
        if code == 'SVP':
            tcg_by_code[('PR-SV', num)] = tc
        if code == 'MEP':
            tcg_by_code[('PR-ME', num)] = tc

    raw.sort(key=lambda r: (r[3], r[0], int(re.sub(r'\D', '', r[1]) or 0)))
    cards, prints, by_key = {}, {}, {}
    for code, num, x, _ in raw:
        c = clean_card(norm_card(x, code))
        pid = f'{code}-{num}'
        tc = tcg_by_code.get((code, num))
        pt = _l(tc['name'], 'pt') if tc else None
        legal = (c['regulation'] in marks) or (c['kind'] == 'energy' and c.get('subtype') == 'basic')
        prints[pid] = {'name': c['name'], 'mark': c['regulation'], 'legal': legal}
        for al in CODE_ALIASES.get(code, []):
            prints[f'{al}-{num}'] = prints[pid]
        if not legal:
            continue
        k = functional_key(c)
        if k not in by_key:
            c['id'] = pid
            c['prints'] = []
            c['name_pt'] = pt
            by_key[k] = c
            cards[pid] = c
        by_key[k]['prints'].append(pid)
        if pt and not by_key[k].get('name_pt'):
            by_key[k]['name_pt'] = pt
        prints[pid]['id'] = by_key[k]['id']
    # impressões antigas (ilegais) apontam para a versão legal de mesmo nome, quando única
    by_name = {}
    for c in cards.values():
        by_name.setdefault(c['name'], []).append(c['id'])
    for pid, p in prints.items():
        if 'id' not in p:
            ids = by_name.get(p['name'], [])
            p['id'] = ids[0] if len(ids) == 1 else None
            if len(ids) > 1:
                p['candidates'] = ids
    for c in cards.values():
        c.pop('regulation', None) if False else None
    out = {'version': 1, 'legal_marks': sorted(marks), 'sets': sets_meta, 'cards': cards, 'prints': prints}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    kinds = {}
    for c in cards.values():
        kinds[c['kind']] = kinds.get(c['kind'], 0) + 1
    print(f'{len(cards)} cartas legais distintas ({kinds}), {len(prints)} impressões indexadas → {a.out}')


if __name__ == '__main__':
    main()
