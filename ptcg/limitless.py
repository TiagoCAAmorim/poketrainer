"""Importador de listas de torneios da Limitless (limitlesstcg.com).

Torneios oficiais (Regionais, Internacionais, Mundial) ficam nas páginas do site; não há API
pública para eles, então este módulo lê o HTML:
    /tournaments?...            lista de torneios
    /tournaments/{id}           classificação (com links /decks/list/{id})
    /decks/list/{id}            lista do deck (links /cards/SET/NUM)
Torneios online (play.limitlesstcg.com) usam a API documentada em docs.limitlesstcg.com.

Seja gentil com o site: há um intervalo entre requisições e cache em disco (.cache/limitless).
"""
from __future__ import annotations

import html as htmllib
import json
import re
import time
import urllib.request
from pathlib import Path

BASE = 'https://limitlesstcg.com'
PLAY_API = 'https://play.limitlesstcg.com/api'
CACHE = Path(__file__).resolve().parent.parent / '.cache' / 'limitless'
UA = 'Mozilla/5.0 (ptcg-sim deck importer; personal research)'
DEFAULT_TYPES = ('regional', 'international', 'world')


class Fetcher:
    def __init__(self, delay=1.5, cache=True, offline_dir=None):
        self.delay, self.cache, self.offline_dir = delay, cache, offline_dir
        self._last = 0.0

    def get(self, url: str) -> str:
        key = re.sub(r'[^A-Za-z0-9]+', '_', url.split('://', 1)[-1])[:180]
        if self.offline_dir:
            p = Path(self.offline_dir) / f'{key}.html'
            if p.exists():
                return p.read_text(encoding='utf-8', errors='replace')
        cp = CACHE / f'{key}.html'
        if self.cache and cp.exists() and time.time() - cp.stat().st_mtime < 7 * 86400:
            return cp.read_text(encoding='utf-8', errors='replace')
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en'})
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode('utf-8', errors='replace')
        self._last = time.time()
        if self.cache:
            CACHE.mkdir(parents=True, exist_ok=True)
            cp.write_text(text, encoding='utf-8')
        return text


def _strip(s: str) -> str:
    s = re.sub(r'<[^>]+>', ' ', s)
    return ' '.join(htmllib.unescape(s).split())


# ------------------------------------------------------------------ lista de torneios
def parse_tournament_list(page: str):
    """→ [{'id', 'name', 'date', 'players', 'format'}] na ordem da página."""
    out, seen = [], set()
    rows = re.findall(r'<tr\b[^>]*>(.*?)</tr>', page, re.S | re.I)
    for row in rows:
        m = re.search(r'href="(?:https?://limitlesstcg\.com)?/tournaments/(\d+)"[^>]*>(.*?)</a>', row, re.S)
        if not m or m.group(1) in seen:
            continue
        tid, name = m.group(1), _strip(m.group(2))
        if not name:
            continue
        cells = [_strip(c) for c in re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)]
        date = next((c for c in cells if re.match(r'^\d{1,2} \w{3} \d{2}$', c)), '')
        players = next((int(c) for c in cells if re.fullmatch(r'\d{2,6}', c)), None)
        fmt = 'standard'
        if re.search(r'alt="[^"]*(?:JP|Japan)[^"]*"|format-jp|STANDARD_JP', row, re.I):
            fmt = 'standard_jp'
        elif re.search(r'expanded|EXP', row):
            fmt = 'expanded'
        seen.add(tid)
        out.append({'id': int(tid), 'name': name, 'date': date, 'players': players, 'format': fmt})
    return out


def classify(name: str) -> str:
    n = name.lower()
    if 'world championship' in n:
        return 'world'
    if 'international' in n or re.search(r'\b(naic|euic|laic|ocic)\b', n):
        return 'international'
    if 'regional' in n:
        return 'regional'
    if 'special event' in n:
        return 'special'
    if 'champions league' in n:
        return 'champions_league'
    if 'national' in n:
        return 'national'
    return 'other'


# ------------------------------------------------------------------ classificação
def parse_standings(page: str, top: int = 8):
    """→ [{'place', 'player', 'list_id', 'archetype'}] (até `top`)."""
    out = []
    rows = re.findall(r'<tr\b([^>]*)>(.*?)</tr>', page, re.S | re.I)
    for attrs, row in rows:
        m = re.search(r'/decks/list/(\d+)', row)
        if not m:
            continue
        place = None
        pm = re.search(r'data-placing="(\d+)"', attrs)
        if pm:
            place = int(pm.group(1))
        else:
            first = re.search(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)
            if first:
                t = _strip(first.group(1))
                if re.fullmatch(r'\d+', t):
                    place = int(t)
        pl = re.search(r'href="[^"]*/players/\d+[^"]*"[^>]*>(.*?)</a>', row, re.S)
        player = _strip(pl.group(1)) if pl else ''
        mons = re.findall(r'/pokemon/(?:gen\d+/)?([a-z0-9\-]+)\.png', row)
        archetype = ' / '.join(x.replace('-', ' ').title() for x in mons) or ''
        out.append({'place': place if place is not None else len(out) + 1, 'player': player,
                    'list_id': int(m.group(1)), 'archetype': archetype})
    out.sort(key=lambda r: r['place'])
    return [r for r in out if r['place'] <= top]


# ------------------------------------------------------------------ lista do deck
def parse_decklist_page(page: str):
    """→ [(qtd, nome, SET, NUM)]. Tenta vários formatos de marcação."""
    cards = []
    # (1) atributos data-set/data-number + spans de quantidade/nome
    for m in re.finditer(r'<div[^>]*class="[^"]*decklist-card[^"]*"[^>]*>(.*?)</div>', page, re.S | re.I):
        block = m.group(0)
        s = re.search(r'data-set="([A-Z0-9\-]+)"', block)
        n = re.search(r'data-number="(\d+[a-z]?)"', block)
        q = re.search(r'card-count[^>]*>\s*(\d+)', block)
        nm = re.search(r'card-name[^>]*>(.*?)<', block, re.S)
        if s and n and q and nm:
            cards.append((int(q.group(1)), _strip(nm.group(1)), s.group(1), n.group(1)))
    if cards:
        return cards
    # (2) links para /cards/SET/NUM cujo texto começa com a quantidade
    for m in re.finditer(r'<a\b[^>]*href="(?:https?://limitlesstcg\.com)?/cards/(?:[a-z]{2}/)?([A-Z0-9\-]+)/(\d+[a-z]?)"[^>]*>(.*?)</a>',
                         page, re.S | re.I):
        text = _strip(m.group(3))
        mm = re.match(r'^(\d+)\s+(.+)$', text)
        if mm:
            cards.append((int(mm.group(1)), mm.group(2), m.group(1), m.group(2)))
    if cards:
        return cards
    # (3) bloco de texto no formato de exportação
    for m in re.finditer(r'<(?:textarea|pre)[^>]*>(.*?)</(?:textarea|pre)>', page, re.S | re.I):
        for line in htmllib.unescape(m.group(1)).splitlines():
            mm = re.match(r'^\s*(\d+)\s+(.+?)\s+([A-Z0-9\-]{2,5})\s+(\d+)\s*$', line)
            if mm:
                cards.append((int(mm.group(1)), mm.group(2), mm.group(3), mm.group(4)))
    return cards


def decklist_text(cards, meta) -> str:
    lines = [f'# {k}: {v}' for k, v in meta.items() if v not in (None, '')]
    lines += [f'{q} {n} {s} {num}' for q, n, s, num in cards]
    return '\n'.join(lines) + '\n'


def slug(s: str) -> str:
    s = re.sub(r"[^\w\s-]", '', s.lower().replace("'", ''))
    return re.sub(r'[\s_-]+', '_', s).strip('_')[:60] or 'x'


# ------------------------------------------------------------------ alto nível
def list_tournaments(fetcher: Fetcher, pages=1, show=100, types=DEFAULT_TYPES, fmt='standard', since=None):
    found = []
    for page in range(1, pages + 1):
        html = fetcher.get(f'{BASE}/tournaments?show={show}&page={page}')
        for t in parse_tournament_list(html):
            t['type'] = classify(t['name'])
            if types and t['type'] not in types:
                continue
            if fmt and t['format'] != fmt:
                continue
            found.append(t)
    return found


def import_tournament(fetcher: Fetcher, tid: int, out_dir: Path, top=8, tournament_name=None, date=''):
    from .decks import parse_decklist, validate
    html = fetcher.get(f'{BASE}/tournaments/{tid}')
    if tournament_name is None:
        m = re.search(r'<title>(.*?)</title>', html, re.S)
        tournament_name = _strip(m.group(1)).split('|')[0].strip() if m else f'Torneio {tid}'
    standings = parse_standings(html, top)
    folder = out_dir / f'{tid}_{slug(tournament_name)}'
    folder.mkdir(parents=True, exist_ok=True)
    report = []
    for st in standings:
        page = fetcher.get(f'{BASE}/decks/list/{st["list_id"]}')
        cards = parse_decklist_page(page)
        meta = {'event': tournament_name, 'date': date, 'place': st['place'], 'player': st['player'],
                'archetype': st['archetype'], 'source': f'{BASE}/decks/list/{st["list_id"]}'}
        text = decklist_text(cards, meta)
        deck, errors = parse_decklist(text, 'x')
        errors += validate(deck.cards) if not errors else []
        name = f'{st["place"]:02d}_{slug(st["player"])}_{slug(st["archetype"])}.txt'
        (folder / name).write_text(text, encoding='utf-8')
        report.append({'file': str(folder / name), 'place': st['place'], 'player': st['player'],
                       'archetype': st['archetype'], 'cards': sum(q for q, *_ in cards), 'errors': errors})
    (folder / 'index.json').write_text(json.dumps({'id': tid, 'name': tournament_name, 'date': date,
                                                   'decks': report}, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        from .logbook import registrar
        registrar('limitless', f'importou {len(report)} decks de {tournament_name} ({date})', pasta=str(folder))
    except Exception:
        pass
    return report


# ------------------------------------------------------------------ API dos torneios online
def online_tournaments(fetcher: Fetcher, fmt='STANDARD', limit=50):
    data = json.loads(fetcher.get(f'{PLAY_API}/tournaments?game=PTCG&format={fmt}&limit={limit}'))
    return data


def online_top_decks(fetcher: Fetcher, tid: str, top=8):
    data = json.loads(fetcher.get(f'{PLAY_API}/tournaments/{tid}/standings'))
    out = []
    for row in sorted(data, key=lambda r: r.get('placing') or 9999)[:top]:
        dl = row.get('decklist') or {}
        cards = []
        for section in ('pokemon', 'trainer', 'energy'):
            for c in dl.get(section, []):
                cards.append((c.get('count', 1), c.get('name'), c.get('set', ''), str(c.get('number', ''))))
        out.append({'place': row.get('placing'), 'player': row.get('name'), 'archetype': (row.get('deck') or {}).get('name'),
                    'cards': cards})
    return out
