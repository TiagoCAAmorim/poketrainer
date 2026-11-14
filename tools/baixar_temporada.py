"""Baixa os N melhores decks de cada torneio oficial de uma temporada (Limitless) → ptcg/data/temporada_2026.json.

    python tools/baixar_temporada.py                       # temporada 2026: 1/set/2025 a 31/ago/2026, top 16
    python tools/baixar_temporada.py --desde 2025-09-01 --ate 2026-08-31 --top 16 --tipos regional international world

O arquivo é versionado e alimenta a página estática (`python tools/build_site.py`). Com cache em .cache/limitless
e intervalo entre requisições, para ser gentil com o site.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ptcg.limitless import BASE, Fetcher, list_tournaments, parse_decklist_page, parse_standings  # noqa: E402

SAIDA = Path(__file__).resolve().parent.parent / 'ptcg' / 'data' / 'temporada_2026.json'


def data(s):
    return datetime.strptime(s, '%d %b %y').date()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--desde', default='2025-09-01')
    ap.add_argument('--ate', default='2026-08-31')
    ap.add_argument('--top', type=int, default=16)
    ap.add_argument('--tipos', nargs='+', default=['regional', 'international', 'world'])
    ap.add_argument('--pages', type=int, default=3)
    ap.add_argument('--delay', type=float, default=1.2)
    ap.add_argument('--saida', default=str(SAIDA))
    a = ap.parse_args()
    desde, ate = datetime.fromisoformat(a.desde).date(), datetime.fromisoformat(a.ate).date()
    f = Fetcher(delay=a.delay)
    ts = [t for t in list_tournaments(f, pages=a.pages, types=set(a.tipos)) if desde <= data(t['date']) <= ate]
    ts.sort(key=lambda t: data(t['date']))
    print(f'{len(ts)} torneios entre {desde} e {ate}', flush=True)
    out = {'desde': a.desde, 'ate': a.ate, 'top': a.top, 'torneios': []}
    for t in ts:
        html = f.get(f'{BASE}/tournaments/{t["id"]}')
        decks = []
        for st in parse_standings(html, a.top):
            cards = parse_decklist_page(f.get(f'{BASE}/decks/list/{st["list_id"]}'))
            decks.append({'place': st['place'], 'player': st['player'], 'archetype': st['archetype'],
                          'list_id': st['list_id'], 'cards': [list(c) for c in cards]})
        out['torneios'].append({'id': t['id'], 'name': t['name'], 'date': str(data(t['date'])), 'type': t['type'],
                                'players': t['players'], 'decks': decks})
        print(f'  {t["date"]}  {t["name"]}: {len(decks)} decks', flush=True)
    Path(a.saida).write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('ok', a.saida)


if __name__ == '__main__':
    main()
