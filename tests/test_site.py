"""Dados da página estática (site/): cartas.js coerente com a base e decks da temporada resolvidos."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ptcg.carddb import db  # noqa: E402

SITE = os.path.join(os.path.dirname(__file__), '..', 'site')


def _js(nome):
    txt = open(os.path.join(SITE, 'data', nome), encoding='utf-8').read()
    return json.loads(txt[txt.index('=') + 1:].rstrip(';'))


def test_imagens():
    d, im = _js('cartas.js'), _js('imagens.js')
    assert im['base'].startswith('https://assets.tcgdex.net/')
    assert set(im['cartas']) <= set(d['cartas'])
    assert len(im['cartas']) > 0.9 * len(d['cartas'])         # quase todas têm ilustração (as promocionais 30C ficam sem)
    assert 'SSP-46' in im['cartas'] or any(k.startswith('SSP-') for k in im['cartas'])


def test_cartas():
    d = _js('cartas.js')
    nomes = {c['n'] for c in d['cartas'].values()}
    assert {c.name for c in db().cards.values()} <= nomes   # a base do site (G, H, I, J) contém toda a do motor
    for cid, c in d['cartas'].items():
        assert c['k'] in 'pte' and c['en'] and c['pt']
        if c['k'] == 'p':
            assert len(c['at']) == len(c['en'][2]) and len(c['ab']) == len(c['en'][1])
            assert len(c['atp']) == len(c['at']) and len(c['abp']) == len(c['ab'])
    assert all(v in d['cartas'] for v in d['impressoes'].values())
    assert 'Basic Fire Energy' in d['nomes']


def test_decks_da_temporada():
    d = _js('decks.js')
    ids = set(_js('cartas.js')['cartas'])
    assert d['torneios']
    for t in d['torneios']:
        assert 1 <= len(t['decks']) <= 16, t['nome']
        for dk in t['decks']:
            assert all(c in ids and n > 0 for c, n in dk['cartas'])
            assert not dk.get('faltam'), (t['nome'], dk['lugar'], dk['faltam'])
            if True:
                assert sum(n for _, n in dk['cartas']) == 60, (t['nome'], dk['lugar'])


if __name__ == '__main__':
    for nome, f in list(globals().items()):
        if nome.startswith('test_'):
            f()
            print('ok', nome)
