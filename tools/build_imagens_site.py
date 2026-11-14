"""Gera site/data/imagens.js: para cada carta do site, o caminho da imagem na TCGdex (assets.tcgdex.net, que permite
CORS — o navegador consegue ler os pixels para simplificar a ilustração). Precisa de rede; resultado em cache.
    python tools/build_imagens_site.py [--refazer]
Formato: window.DADOS_IMAGENS = {"base": "https://assets.tcgdex.net/en/", "cartas": {"SSP-46": "sv/sv08/046", ...}}
(a imagem é base + caminho + "/low.webp")."""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / 'site' / 'data' / 'imagens.js'
CACHE = RAIZ / '.cache' / 'tcgdex_imagens_site.json'
API = 'https://api.tcgdex.net/v2/en'
BASE = 'https://assets.tcgdex.net/en/'
ALIAS = {'PR-SV': 'SVP', 'PR-ME': 'MEP'}   # nosso código → abreviação oficial na TCGdex


def http(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'ptcg-lab site builder'})
            return json.load(urllib.request.urlopen(req, timeout=30))
        except Exception as e:   # noqa: BLE001
            err = e
            time.sleep(1.5 * (i + 1))
    print('falhou', url, err, file=sys.stderr)
    return None


def indice(refazer):
    if CACHE.exists() and not refazer:
        return json.loads(CACHE.read_text(encoding='utf-8'))
    out = {}
    for s in http(f'{API}/sets') or []:
        if not s['id'].startswith(('sv', 'me')):
            continue
        d = http(f'{API}/sets/{s["id"]}')
        if not d:
            continue
        abbr = ((d.get('abbreviation') or {}).get('official') or '').upper()
        for c in d.get('cards', []):
            if c.get('image') and abbr:
                out.setdefault(abbr, {})[str(c['localId']).lstrip('0').lower() or '0'] = c['image'].replace(BASE, '')
        time.sleep(0.15)
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(out), encoding='utf-8')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refazer', action='store_true')
    a = ap.parse_args()
    txt = (RAIZ / 'site' / 'data' / 'cartas.js').read_text(encoding='utf-8')
    dados = json.loads(txt[txt.index('=') + 1:].rstrip(';'))
    ind = indice(a.refazer)
    cartas, sem = {}, []
    por_id = {}
    for pr, cid in dados['impressoes'].items():
        por_id.setdefault(cid, []).append(pr)
    for cid in dados['cartas']:
        achou = None
        for pr in [cid] + por_id.get(cid, []):
            code, num = pr.rsplit('-', 1)
            achou = ind.get(ALIAS.get(code, code), {}).get(num.lstrip('0').lower() or '0')
            if achou:
                break
        if achou:
            cartas[cid] = achou
        else:
            sem.append(cid)
    SAIDA.write_text('window.DADOS_IMAGENS=' + json.dumps({'base': BASE, 'cartas': cartas}, separators=(',', ':')) + ';', encoding='utf-8')
    print(f'imagens.js: {len(cartas)} cartas com imagem, {len(sem)} sem ({", ".join(sem[:12])}{"…" if len(sem) > 12 else ""})')


if __name__ == '__main__':
    main()
