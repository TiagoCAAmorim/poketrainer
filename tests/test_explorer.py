"""Testes da exploração de cartas (ptcg/explorer.py): filtros, detalhe e proteção do caminho das imagens."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ptcg import explorer as EX  # noqa: E402
from ptcg.carddb import db  # noqa: E402


def test_filtros():
    o = EX.opcoes()
    assert o['total'] == len(db().cards) == sum(o['status'].values())
    assert EX.filtrar('dr')['cards'] == [] and EX.filtrar('dr')['dica']          # < 3 letras
    prob = EX.filtrar(status='problema')
    assert prob['total'] == o['status']['parcial'] + o['status']['pendente']
    assert all(c['status'] != 'ok' and c['pendencias'] for c in prob['cards'])
    assert EX.filtrar(status='missing')['total'] == o['status']['pendente']
    assert all(c['status'] == 'ok' for c in EX.filtrar(status='ok')['cards'])
    r = EX.filtrar(grupo='Pokemon_EX', tipo='R', estagio='0')
    assert r['total'] and all(c['ex'] and c['stage'] == 0 and 'R' in c['types'] for c in r['cards'])
    assert EX.filtrar(colecao='ASC')['total'] > 0
    assert len(EX.filtrar(status='')['cards']) == EX.PAGINA                       # paginação
    p2 = EX.filtrar(status='', offset=EX.PAGINA)
    assert p2['cards'][0]['id'] != EX.filtrar(status='')['cards'][0]['id']
    # busca no texto dos efeitos encontra mais que só no nome
    assert EX.filtrar('discard', no_texto=True)['total'] > EX.filtrar('discard')['total']


def test_detalhe_e_imagens():
    d = EX.detalhe('TWM-130')
    assert d['name'] == 'Dragapult ex' and d['ataques'][1]['texto_pt'] and d['impressoes'][0]['colecao']
    pend = next(c for c in db().cards.values() if c.status != 'ok')
    assert EX.detalhe(pend.id)['pendencias']
    assert EX.arquivo_imagem('baixa', '../../etc/passwd') is None                 # só IDs da base
    f = EX.arquivo_imagem('../x', 'TWM-130')                                       # qualidade inválida → baixa
    assert f is None or EX.IMG_DIR in f.parents


if __name__ == '__main__':
    test_filtros()
    test_detalhe_e_imagens()
    print('ok')
