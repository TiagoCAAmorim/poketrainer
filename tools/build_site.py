"""Gera os dados da página estática de PDFs (site/data/*.js).

    python tools/build_carddb.py --marks G,H,I,J --out .cache/cards_site.json
    python tools/build_pt_texts.py --cards .cache/cards_site.json --out .cache/cards_pt_site.json
    python tools/baixar_temporada.py
    python tools/build_site.py

A página usa uma base PRÓPRIA (marcas G, H, I, J), maior que a do motor (H, I, J), porque os decks da temporada
2026 ainda usam cartas da marca G. A base do motor não é tocada.

- cartas.js : cartas em formato compacto, com textos em inglês e português, impressões (SET-NUM → id) e nomes;
- decks.js  : top 16 dos torneios da temporada (ptcg/data/temporada_2026.json), com as cartas resolvidas para ids.
              Decks com carta desconhecida entram marcados com `faltam`.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SAIDA = RAIZ / 'site' / 'data'
TEMPORADA = RAIZ / 'ptcg' / 'data' / 'temporada_2026.json'
ERRATA = RAIZ / 'ptcg' / 'data' / 'errata.json'
KIND = {'pokemon': 'p', 'trainer': 't', 'energy': 'e'}


def dano(s):
    """Mesmo critério de ptcg.carddb.parse_damage: '30x' → '30×'; texto livre → ''."""
    m = re.match(r'^(\d+)\s*([+×\-]?)$', (s or '').strip().replace('x', '×'))
    return f'{int(m.group(1))}{m.group(2)}' if m else ''


def aplicar_errata(c, errata):
    fix = errata.get(c['name'])
    if not fix:
        return c
    c = json.loads(json.dumps(c))
    for a in c.get('abilities') or []:
        a['text'] = fix.get('abilities', {}).get(a['name'], a['text'])
    for a in c.get('attacks') or []:
        a['text'] = fix.get('attacks', {}).get(a['name'], a['text'])
    if 'text' in fix:
        c['text'] = fix['text']
    return c


def carta(c, pt):
    """Carta compacta. `pt`: entrada de cards_pt (ou {}). Textos por idioma: [texto, [habilidades], [ataques]]."""
    ab, at = c.get('abilities') or [], c.get('attacks') or []
    pab, pat = pt.get('abilities') or [], pt.get('attacks') or []
    o = {'n': c['name'], 'k': KIND[c['kind']]}
    nome_pt = pt.get('name') or c.get('name_pt') or ''
    if nome_pt and nome_pt != c['name']:
        o['p'] = nome_pt
    if c['kind'] == 'pokemon':
        o.update(s=c.get('stage', 0), t=list(c.get('types') or []), h=c.get('hp', 0), rt=c.get('retreat', 0))
        if c.get('evolves_from'):
            o['f'] = c['evolves_from']
        if c.get('weakness'):
            o['w'] = c['weakness']
        if c.get('resistance'):
            o['r'], o['rv'] = c['resistance'], c.get('resistance_value') or 30
        o['at'] = [[a['name'], list(a.get('cost') or []), dano(a.get('damage'))] for a in at]
        o['ab'] = [[a['name']] for a in ab]
        o['abp'] = [(pab[i].get('name') if i < len(pab) else '') or a['name'] for i, a in enumerate(ab)]
        o['atp'] = [(pat[i].get('name') if i < len(pat) else '') or a['name'] for i, a in enumerate(at)]
    elif c['kind'] == 'trainer':
        o['st'] = c.get('subtype')
        if 'ace_spec' in (c.get('tags') or []):
            o['a'] = 1
    else:
        o['b'] = 1 if c.get('subtype') == 'basic' else 0
        if c.get('provides'):
            o['pv'] = c['provides']
    o['en'] = [c.get('text') or '', [a.get('text') or '' for a in ab], [a.get('text') or '' for a in at]]
    o['pt'] = [pt.get('text') or c.get('text') or '',
               [((pab[i].get('text') if i < len(pab) else '') or a.get('text') or '') for i, a in enumerate(ab)],
               [((pat[i].get('text') if i < len(pat) else '') or a.get('text') or '') for i, a in enumerate(at)]]
    return o


def escrever(arquivo, var, dados):
    """Grava `window.VAR = {...};` (um .js, para a página abrir até por duplo clique, sem servidor)."""
    (SAIDA / arquivo).write_text(f'window.{var}=' + json.dumps(dados, ensure_ascii=False, separators=(',', ':')) + ';',
                                 encoding='utf-8')


def norm(s):
    return re.sub(r'\s+', ' ', (s or '').replace('’', "'").lower()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cards', default=str(RAIZ / '.cache' / 'cards_site.json'))
    ap.add_argument('--cards-pt', default=str(RAIZ / '.cache' / 'cards_pt_site.json'))
    a = ap.parse_args()
    if not Path(a.cards).exists():
        sys.exit(f'Falta {a.cards}: veja os comandos no topo deste arquivo.')
    raw = json.load(open(a.cards, encoding='utf-8'))
    pt = json.load(open(a.cards_pt, encoding='utf-8')) if Path(a.cards_pt).exists() else {}
    errata = json.load(open(ERRATA, encoding='utf-8')) if ERRATA.exists() else {}
    SAIDA.mkdir(parents=True, exist_ok=True)

    cartas = {cid: carta(aplicar_errata(c, errata), pt.get(cid) or {}) for cid, c in sorted(raw['cards'].items())}
    impressoes = {k: v['id'] for k, v in raw['prints'].items() if v.get('id') in cartas}
    nomes = {}   # nome (en) → id preferido
    for cid, c in cartas.items():
        nomes.setdefault(c['n'], cid)
    escrever('cartas.js', 'DADOS_CARTAS', {'cartas': cartas, 'impressoes': impressoes, 'nomes': nomes})
    print(f'cartas.js: {len(cartas)} cartas, {len(impressoes)} impressões')

    if not TEMPORADA.exists():
        print('sem temporada_2026.json (rode tools/baixar_temporada.py)')
        return
    temp = json.loads(TEMPORADA.read_text(encoding='utf-8'))
    por_nome = {norm(n): i for n, i in nomes.items()}
    for en in ('Grass', 'Fire', 'Water', 'Lightning', 'Psychic', 'Fighting', 'Darkness', 'Metal'):
        if f'Basic {en} Energy' in nomes:
            por_nome.setdefault(norm(f'{en} Energy'), nomes[f'Basic {en} Energy'])

    def resolver(nome, st, num):
        n = str(num).lstrip('0') or '0'
        for code in (st.upper(), st.upper().replace('PR-', '')):
            i = impressoes.get(f'{code}-{n}')
            if i:
                return i
        return por_nome.get(norm(nome))

    torneios, faltam_total = [], Counter()
    for t in temp['torneios']:
        decks = []
        for dk in t['decks']:
            cont, faltam = Counter(), []
            for q, nome, st, num in dk['cards']:
                cid = resolver(nome, st, num)
                if cid:
                    cont[cid] += q
                else:
                    faltam.append(f'{q} {nome} {st} {num}')
                    faltam_total[nome] += q
            decks.append({'lugar': dk['place'], 'jogador': dk['player'], 'arq': dk['archetype'],
                          'cartas': [[c, n] for c, n in cont.items()], **({'faltam': faltam} if faltam else {})})
        torneios.append({'id': t['id'], 'nome': t['name'], 'data': t['date'], 'tipo': t['type'], 'jogadores': t['players'],
                         'decks': decks})
    escrever('decks.js', 'DADOS_DECKS', {'desde': temp['desde'], 'ate': temp['ate'], 'torneios': torneios})
    n = sum(len(t['decks']) for t in torneios)
    comfalta = sum(1 for t in torneios for d in t['decks'] if d.get('faltam'))
    print(f'decks.js: {len(torneios)} torneios, {n} decks ({comfalta} com cartas fora da base)')
    for nome, q in faltam_total.most_common(15):
        print('  fora da base:', nome, q)


if __name__ == '__main__':
    main()
