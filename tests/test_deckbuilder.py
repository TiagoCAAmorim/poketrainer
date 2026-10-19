"""Testes do montador de decks (ptcg/deckbuilder.py): busca, categorias, salvar e duplicar (em pasta temporária)."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ptcg import deckbuilder as DB, decks  # noqa: E402
from ptcg.decks import DECK_DIR  # noqa: E402


def test_busca_e_categorias():
    assert DB.buscar('ab')['cards'] == []                       # menos de 3 letras e sem categoria
    r = DB.buscar('dragapult')
    assert any(c['name'] == 'Dragapult ex' and c['ex'] for c in r['cards'])
    assert DB.buscar('ultra bola')['cards'][0]['name'] == 'Ultra Ball'   # nome em português
    ap = DB.buscar('', 'Treinadores', 'Apoiadores')
    assert ap['total'] > 0 and all(c['sub'] == 'Apoiadores' for c in ap['cards'])
    ex = DB.buscar('', 'Pokemon_EX', 'Fogo')
    assert ex['total'] > 0 and all(c['ex'] and 'R' in c['types'][:1] for c in ex['cards'])
    assert DB.buscar('dragapult', 'Energias')['cards'] == []     # filtros se combinam
    assert sum(c['n'] for c in DB.lista_categorias()) == len(DB.db().cards)


def test_salvar_e_duplicar():
    tmp = Path(tempfile.mkdtemp())
    orig = (DB.DECK_DIR, decks.DECK_DIR)
    # origem: deck real de decks/tests; destino: pasta temporária
    base = decks.load_deck('tests/01_hedrick_dragapult')
    try:
        DB.DECK_DIR = decks.DECK_DIR = tmp
        (tmp / 'tests').mkdir()
        (tmp / 'tests' / 'origem.txt').write_text((orig[1] / 'tests' / '01_hedrick_dragapult.txt').read_text(encoding='utf-8'),
                                                  encoding='utf-8')
        r = DB.duplicar('tests/origem', 'minha_copia')
        assert r['name'] == 'meus/minha_copia' and r['total'] == 60 and not r['errors']
        v = DB.ver_deck('meus/minha_copia')
        assert v['editavel'] and v['meta']['copiado_de'] == 'tests/origem' and v['total'] == 60
        try:
            DB.duplicar('tests/origem', 'minha_copia')
            raise AssertionError('deveria recusar nome existente')
        except FileExistsError:
            pass
        assert DB.duplicar('tests/origem')['name'] == 'meus/origem'
        assert DB.duplicar('tests/origem')['name'] == 'meus/origem_2'
        itens = [{'id': c['id'], 'n': c['n']} for c in v['cards']]
        itens[0]['n'] -= 1
        r = DB.salvar('minha_copia', itens, sobrescrever=True)
        assert not r['criado'] and r['total'] == 59 and r['errors']
        try:
            DB.salvar('minha_copia', itens, sobrescrever=False)
            raise AssertionError('deveria recusar sobrescrita')
        except FileExistsError:
            pass
        assert [d['name'] for d in DB.decks_disponiveis() if d['meu']][0].startswith('meus/')
        assert sum(c['n'] for c in DB.ver_deck('meus/minha_copia')['cards']) == 59
    finally:
        DB.DECK_DIR, decks.DECK_DIR = orig
    assert base.cards and DECK_DIR == orig[1]


if __name__ == '__main__':
    test_busca_e_categorias()
    test_salvar_e_duplicar()
    print('ok')
