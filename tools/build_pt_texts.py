"""Extrai do TCGdex os textos oficiais em português (nomes, ataques, Habilidades, efeitos de Treinador).

    python tools/build_pt_texts.py --tcgdex /caminho/cards-database
Gera ptcg/data/cards_pt.json: {id_da_carta: {name, attacks:[{name,text}], abilities:[{name,text}], text}}.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import re  # noqa: E402

from tools.build_carddb import CACHE, git_clone, load_tcgdex  # noqa: E402

SYM_PT = {'G': 'Planta', 'R': 'Fogo', 'W': 'Água', 'L': 'Elétrico', 'P': 'Psíquico', 'F': 'Lutador',
          'D': 'Escuridão', 'M': 'Metal', 'N': 'Dragão', 'C': 'Incolor', 'Y': 'Fada'}


def clean_text(t):
    if not t:
        return t
    t = re.sub(r'\{([GRWLPFDMNCY])\}', lambda m: SYM_PT[m.group(1)], t)
    t = t.replace('’', "'").replace('“', '"').replace('”', '"').replace('\u00a0', ' ')
    return re.sub(r'\s+', ' ', t).strip()

ROOT = Path(__file__).resolve().parents[1]
ALIAS = {'SVP': 'PR-SV', 'MEP': 'PR-ME'}


def pt(d):
    if isinstance(d, dict):
        return d.get('pt') or d.get('pt-br')
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tcgdex', default=None)
    a = ap.parse_args()
    tdir = Path(a.tcgdex) if a.tcgdex else git_clone('https://github.com/tcgdex/cards-database', CACHE / 'tcgdex',
                                                     sparse=['data/Scarlet & Violet', 'data/Mega Evolution'])
    tc, _ = load_tcgdex(tdir)
    by = {}
    for (code, num), c in tc.items():
        by[(ALIAS.get(code, code), num)] = c
    data = json.load(open(ROOT / 'ptcg' / 'data' / 'cards.json', encoding='utf-8'))
    out = {}
    for cid, card in data['cards'].items():
        best = None
        for p in card['prints']:
            code, num = p.rsplit('-', 1)
            c = by.get((code, num.lstrip('0') or '0'))
            if c is not None and pt(c.get('name')):
                best = c
                if any(pt(x.get('effect')) for x in (c.get('attacks') or []) + (c.get('abilities') or [])) \
                        or pt(c.get('effect')) or card['kind'] == 'energy':
                    break
        if best is None:
            continue
        e = {'name': pt(best['name'])}
        if best.get('attacks'):
            e['attacks'] = [{'name': pt(x.get('name')) or '', 'text': clean_text(pt(x.get('effect')) or '')}
                            for x in best['attacks']]
        if best.get('abilities'):
            e['abilities'] = [{'name': pt(x.get('name')) or '', 'text': clean_text(pt(x.get('effect')) or '')}
                              for x in best['abilities']]
        if pt(best.get('effect')):
            e['text'] = clean_text(pt(best['effect']))
        out[cid] = e
    dst = ROOT / 'ptcg' / 'data' / 'cards_pt.json'
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(out)}/{len(data["cards"])} cartas com texto em português → {dst}')


if __name__ == '__main__':
    main()
