"""Baixa as imagens das cartas do formato para imagens/cartas/ (pasta fora do git).

Fonte principal: TCGdex (assets.tcgdex.net, .webp leve); reserva: images.pokemontcg.io (.png).
Cada carta usa a primeira impressão que tiver imagem. É retomável: o que já foi baixado é pulado.

    imagens/cartas/baixa/<ID>.webp    miniatura (~17 KB) para listas e grades
    imagens/cartas/alta/<ID>.webp     imagem grande (~75 KB) para o detalhe da carta
    imagens/indice.json               carta → fonte/URLs usadas (e as sem imagem)

Exemplos:
    python baixar_imagens.py                       # baixa tudo (baixa + alta)
    python baixar_imagens.py --qualidade baixa     # só as miniaturas (mais rápido)
    python baixar_imagens.py --nome "Dragapult"    # só cartas cujo nome contém o texto
    python baixar_imagens.py --colecao ASC MEG     # só estas coleções
    python baixar_imagens.py --refazer             # baixa de novo mesmo as que já existem
    python baixar_imagens.py --listar-faltantes    # mostra as cartas sem imagem baixada

Use com cuidado de rede: há uma pausa entre as requisições (--delay) e 4 conexões em paralelo (--threads).
"""
import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ptcg.carddb import db, norm

ROOT = Path(__file__).resolve().parent
IMG_DIR = ROOT / 'imagens'
CARTAS = IMG_DIR / 'cartas'
INDICE = IMG_DIR / 'indice.json'
UA = {'User-Agent': 'Mozilla/5.0 (ptcg-lab image fetcher)'}
TCGDEX = 'https://api.tcgdex.net/v2/en'
PTCGIO = 'https://images.pokemontcg.io'
ALIAS_COLECAO = {'PR-SV': 'SVP', 'PR-ME': 'MEP'}   # nosso código → abreviação oficial na TCGdex


def http(url, binary=False, tries=4, timeout=30):
    """GET com novas tentativas em 5xx/erros de rede. Devolve None em 404/403."""
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                data = r.read()
                return data if binary else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            err = e
        except Exception as e:   # rede
            err = e
        time.sleep(1.5 * (i + 1))
    print(f'  falhou {url}: {err}', file=sys.stderr)
    return None


def num_key(n):
    n = str(n).strip().lower()
    return n.lstrip('0') or '0'


def tcgdex_index(delay):
    """{abreviação oficial: {número: url_base_da_imagem}} para as coleções das séries sv e me."""
    sets = http(f'{TCGDEX}/sets') or []
    out = {}
    for s in sets:
        if not (s['id'].startswith(('sv', 'me'))):
            continue
        d = http(f'{TCGDEX}/sets/{s["id"]}')
        time.sleep(delay)
        if not d:
            continue
        abbr = ((d.get('abbreviation') or {}).get('official') or '').upper()
        if not abbr:
            continue
        cards = {num_key(c['localId']): c['image'] for c in d.get('cards', []) if c.get('image')}
        out.setdefault(abbr, {}).update(cards)
    return out


def candidatas(card, tdx, setids):
    """Fontes possíveis em ordem: TCGdex de cada impressão, depois pokemontcg.io de cada impressão."""
    fontes = []
    for pr in card.prints or [card.id]:
        code, num = pr.rsplit('-', 1)
        base = tdx.get(ALIAS_COLECAO.get(code, code), {}).get(num_key(num))
        if base:
            fontes.append(('tcgdex', {'baixa': f'{base}/low.webp', 'alta': f'{base}/high.webp'}))
    for pr in card.prints or [card.id]:
        code, num = pr.rsplit('-', 1)
        sid = setids.get(code)
        if sid:
            fontes.append(('pokemontcg.io', {'baixa': f'{PTCGIO}/{sid}/{num}.png',
                                               'alta': f'{PTCGIO}/{sid}/{num}_hires.png'}))
    return fontes


def caminho(qual, cid, fonte):
    ext = 'webp' if fonte == 'tcgdex' else 'png'
    return CARTAS / qual / f'{cid}.{ext}'


def existente(qual, cid):
    for ext in ('webp', 'png'):
        p = CARTAS / qual / f'{cid}.{ext}'
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def baixar_carta(card, tdx, setids, quals, refazer, delay):
    cid = card.id
    if not refazer and all(existente(q, cid) for q in quals):
        return cid, 'ja_existia', None
    for fonte, urls in candidatas(card, tdx, setids):
        ok = True
        info = {'fonte': fonte, 'urls': urls}
        for q in quals:
            if not refazer and existente(q, cid):
                continue
            data = http(urls[q], binary=True)
            time.sleep(delay)
            if not data or len(data) < 500:
                ok = False
                break
            p = caminho(q, cid, fonte)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        if ok:
            return cid, 'baixada', info
    return cid, 'sem_imagem', None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--qualidade', choices=['baixa', 'alta', 'ambas'], default='ambas')
    ap.add_argument('--nome', default=None, help='só cartas cujo nome (en/pt) contém o texto')
    ap.add_argument('--colecao', nargs='*', default=None, help='só cartas com impressão nestas coleções (ex.: ASC MEG)')
    ap.add_argument('--refazer', action='store_true')
    ap.add_argument('--listar-faltantes', action='store_true')
    ap.add_argument('--threads', type=int, default=4)
    ap.add_argument('--delay', type=float, default=0.15, help='pausa (s) após cada requisição de cada conexão')
    a = ap.parse_args()
    quals = ['baixa', 'alta'] if a.qualidade == 'ambas' else [a.qualidade]

    D = db()
    cards = list(D.cards.values())
    if a.nome:
        n = norm(a.nome)
        cards = [c for c in cards if n in norm(c.name) or (c.name_pt and n in norm(c.name_pt))]
    if a.colecao:
        cols = {c.upper() for c in a.colecao}
        cards = [c for c in cards if any(p.rsplit('-', 1)[0] in cols for p in (c.prints or [c.id]))]
    if a.listar_faltantes:
        falt = [c for c in cards if not all(existente(q, c.id) for q in quals)]
        for c in falt:
            print(f'{c.id}\t{c.name}')
        print(f'{len(falt)} de {len(cards)} cartas sem imagem baixada.')
        return

    sets_json = json.load(open(ROOT / 'ptcg' / 'data' / 'cards.json', encoding='utf-8'))['sets']
    setids = {k: v['id'] for k, v in sets_json.items()}
    print('Lendo o índice de imagens da TCGdex…')
    tdx = tcgdex_index(a.delay)
    print(f'  {sum(len(v) for v in tdx.values())} imagens em {len(tdx)} coleções')

    indice = json.load(open(INDICE, encoding='utf-8')) if INDICE.exists() else {}
    stats = {'baixada': 0, 'ja_existia': 0, 'sem_imagem': 0}
    sem = []
    lock = threading.Lock()
    print(f'Baixando {len(cards)} cartas ({", ".join(quals)}) para {CARTAS.relative_to(ROOT)}/ …')
    with ThreadPoolExecutor(max_workers=max(1, a.threads)) as ex:
        futs = [ex.submit(baixar_carta, c, tdx, setids, quals, a.refazer, a.delay) for c in cards]
        for i, f in enumerate(as_completed(futs), 1):
            cid, st, info = f.result()
            with lock:
                stats[st] += 1
                if info:
                    indice[cid] = info
                if st == 'sem_imagem':
                    sem.append(cid)
            if i % 100 == 0 or i == len(futs):
                print(f'  {i}/{len(futs)}  novas {stats["baixada"]}  já existiam {stats["ja_existia"]}  sem imagem {stats["sem_imagem"]}')
    IMG_DIR.mkdir(exist_ok=True)
    indice['_sem_imagem'] = sorted(set(indice.get('_sem_imagem', [])) - {c.id for c in cards} | set(sem))
    INDICE.write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Pronto: {stats["baixada"]} baixadas, {stats["ja_existia"]} já existiam, {stats["sem_imagem"]} sem imagem.')
    if sem:
        print('Sem imagem (veja também imagens/indice.json): ' + ', '.join(sorted(sem)[:20]) + (' …' if len(sem) > 20 else ''))


if __name__ == '__main__':
    main()
