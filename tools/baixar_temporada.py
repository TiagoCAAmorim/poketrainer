"""Baixa os N melhores decks de cada torneio oficial de uma temporada (Limitless) → ptcg/data/temporada_AAAA.json.

    python tools/baixar_temporada.py                       # temporada atual (set–ago; AAAA = ano em que termina), top 16
    python tools/baixar_temporada.py --desde 2025-09-01 --ate 2026-08-31 --saida ptcg/data/temporada_2026.json
    python tools/baixar_temporada.py --refazer             # ignora o que já está no arquivo

É incremental: torneios já presentes no arquivo (por id) não são baixados de novo, e torneios de hoje (ainda em
andamento) são ignorados. O arquivo é versionado e alimenta a página estática (`python tools/build_site.py`).
Com cache em .cache/limitless e intervalo entre requisições, para ser gentil com o site.
"""
import argparse
import json
import sys
from datetime import date as Date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ptcg.limitless import BASE, Fetcher, list_tournaments, parse_decklist_page, parse_standings  # noqa: E402

SAIDA = Path(__file__).resolve().parent.parent / 'ptcg' / 'data' / 'temporada_2026.json'   # só a pasta importa


def data(s):
    return datetime.strptime(s, '%d %b %y').date()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--desde', default=None, help='padrão: 1/set da temporada atual')
    ap.add_argument('--ate', default=None, help='padrão: 31/ago da temporada atual')
    ap.add_argument('--refazer', action='store_true')
    ap.add_argument('--top', type=int, default=16)
    ap.add_argument('--tipos', nargs='+', default=['regional', 'international', 'world'])
    ap.add_argument('--pages', type=int, default=3)
    ap.add_argument('--delay', type=float, default=1.2)
    ap.add_argument('--saida', default=None, help='padrão: ptcg/data/temporada_AAAA.json')
    a = ap.parse_args()
    hoje = Date.today()
    ano = hoje.year + (1 if hoje.month >= 9 else 0)   # a temporada 2027 vai de set/2026 a ago/2027
    a.desde = a.desde or f'{ano - 1}-09-01'
    a.ate = a.ate or f'{ano}-08-31'
    saida = Path(a.saida) if a.saida else SAIDA.parent / f'temporada_{a.ate[:4]}.json'
    desde, ate = datetime.fromisoformat(a.desde).date(), datetime.fromisoformat(a.ate).date()
    antigos = {}
    if saida.exists() and not a.refazer:
        antigos = {t['id']: t for t in json.loads(saida.read_text(encoding='utf-8'))['torneios']}
    f = Fetcher(delay=a.delay)
    ts = [t for t in list_tournaments(f, pages=a.pages, types=set(a.tipos)) if desde <= data(t['date']) <= min(ate, hoje - timedelta(days=1))]
    ts.sort(key=lambda t: data(t['date']))
    print(f'{len(ts)} torneios entre {desde} e {ate}', flush=True)
    out = {'desde': a.desde, 'ate': a.ate, 'top': a.top, 'torneios': []}
    for t in ts:
        if t['id'] in antigos:
            out['torneios'].append(antigos[t['id']])
            print(f'  {t["date"]}  {t["name"]}: já baixado', flush=True)
            continue
        html = f.get(f'{BASE}/tournaments/{t["id"]}')
        decks = []
        for st in parse_standings(html, a.top):
            cards = parse_decklist_page(f.get(f'{BASE}/decks/list/{st["list_id"]}'))
            decks.append({'place': st['place'], 'player': st['player'], 'archetype': st['archetype'],
                          'list_id': st['list_id'], 'cards': [list(c) for c in cards]})
        out['torneios'].append({'id': t['id'], 'name': t['name'], 'date': str(data(t['date'])), 'type': t['type'],
                                'players': t['players'], 'decks': decks})
        print(f'  {t["date"]}  {t["name"]}: {len(decks)} decks', flush=True)
    saida.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('ok', saida)


if __name__ == '__main__':
    main()
