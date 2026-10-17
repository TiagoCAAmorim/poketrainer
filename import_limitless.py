"""Baixa os decks do top 8 de torneios oficiais da Limitless para decks/limitless/.

Exemplos:
    python import_limitless.py list                      # torneios recentes (Regional/Internacional/Mundial)
    python import_limitless.py list --types regional international world special
    python import_limitless.py import --latest 5         # top 8 dos 5 torneios mais recentes
    python import_limitless.py import --ids 581 515      # torneios específicos
    python import_limitless.py import --latest 10 --top 16
    python import_limitless.py online --latest 3         # torneios online (API play.limitlesstcg.com)

Depois:  python simulate.py decks/limitless/581_*/  --games 200
"""
import argparse
import sys
from pathlib import Path

from ptcg.limitless import DEFAULT_TYPES, Fetcher, decklist_text, import_tournament, list_tournaments, \
    online_top_decks, online_tournaments, slug

OUT = Path(__file__).resolve().parent / 'decks' / 'limitless'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('list', 'import'):
        s = sub.add_parser(name)
        s.add_argument('--types', nargs='+', default=list(DEFAULT_TYPES),
                       help='regional international world special national champions_league other')
        s.add_argument('--format', default='standard', help='standard | standard_jp | expanded')
        s.add_argument('--pages', type=int, default=1)
        s.add_argument('--delay', type=float, default=1.5, help='segundos entre requisições')
        s.add_argument('--offline', default=None, help='pasta com páginas HTML salvas')
    sub.choices['import'].add_argument('--ids', nargs='*', type=int, default=[])
    sub.choices['import'].add_argument('--latest', type=int, default=0)
    sub.choices['import'].add_argument('--top', type=int, default=8)
    on = sub.add_parser('online')
    on.add_argument('--latest', type=int, default=3)
    on.add_argument('--top', type=int, default=8)
    on.add_argument('--format', default='STANDARD')
    a = ap.parse_args()

    if a.cmd == 'online':
        f = Fetcher()
        for t in online_tournaments(f, a.format, limit=a.latest):
            folder = OUT / 'online' / f'{t["id"]}_{slug(t["name"])}'
            folder.mkdir(parents=True, exist_ok=True)
            for d in online_top_decks(f, t['id'], a.top):
                meta = {'event': t['name'], 'date': t.get('date', ''), 'place': d['place'], 'player': d['player'],
                        'archetype': d['archetype']}
                (folder / f'{d["place"]:02d}_{slug(d["player"] or "x")}.txt').write_text(
                    decklist_text(d['cards'], meta), encoding='utf-8')
            print('ok', folder)
        return 0

    f = Fetcher(delay=a.delay, offline_dir=a.offline)
    ts = list_tournaments(f, pages=a.pages, types=set(a.types), fmt=a.format)
    if a.cmd == 'list':
        for t in ts:
            print(f'{t["id"]:>6}  {t["date"]:>10}  {t["type"]:<14} {t["players"] or "":>6}  {t["name"]}')
        return 0
    targets = list(a.ids)
    names = {t['id']: t for t in ts}
    if a.latest:
        targets += [t['id'] for t in ts[:a.latest] if t['id'] not in targets]
    if not targets:
        print('Nada para importar (use --ids ou --latest).')
        return 1
    bad = 0
    for tid in targets:
        info = names.get(tid, {})
        print(f'\n== {tid} {info.get("name", "")}')
        rep = import_tournament(f, tid, OUT, a.top, info.get('name'), info.get('date', ''))
        for r in rep:
            flag = 'ok ' if not r['errors'] else 'ERRO'
            bad += bool(r['errors'])
            print(f'  {flag} {r["place"]:>2}. {r["player"]:<24} {r["archetype"]:<28} {r["cards"]} cartas'
                  + (f'  → {r["errors"][:2]}' if r['errors'] else ''))
    print('\nDecks salvos em', OUT)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
