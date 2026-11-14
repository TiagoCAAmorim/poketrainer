"""Teste de deck (ptcg/testdeck.py): estatísticas, instrumentação do motor, sugestões e salvar versão."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ptcg import deckbuilder as DB, decks, testdeck as TD  # noqa: E402
from ptcg.agents import make_agent, play_game  # noqa: E402
from ptcg.decks import load_deck  # noqa: E402

A, B = 'tests/01_hedrick_dragapult', 'tests/08_spry_basic_box'


def test_motor_registra_jogadas_e_premios():
    a, b = load_deck(A).cards, load_deck(B).cards
    g = play_game(a, b, [make_agent('heuristic', seed=1), make_agent('heuristic', seed=2)], seed=3)
    assert g.plays and {p[2] for p in g.plays} >= {'treinador', 'energia', 'ataque'}
    assert all(t >= 1 for t, *_ in g.plays)
    # prêmios registrados batem com os prêmios realmente pegos, e a vez só cresce para cada jogador
    for p in (0, 1):
        assert sum(n for _, q, n in g.prize_turns if q == p) == g.prizes_taken(p)
        ts = [t for t, q, _ in g.prize_turns if q == p]
        assert ts == sorted(ts)


def test_testar_deck_estatisticas():
    ops, _ = TD.listar_oponentes(A, 'tests/', 3, seed=1)
    assert 1 <= len(ops) <= 3 and all(o['name'] != A for o in ops)
    r = TD.testar_deck(A, partidas=6, oponentes=ops, workers=2)
    assert r['jogos'] == 6 * len(ops) and 0 <= r['winrate'] <= 1
    assert r['ordem']['primeiro']['jogos'] + r['ordem']['segundo']['jogos'] == r['jogos']
    assert sum(c['copias'] for c in r['cartas']) == 60
    assert all(0 <= c['vista_pct'] <= 1 and 0 <= c['usada_pct'] <= 1 for c in r['cartas'])
    h = r['premios']['meu']
    assert len(h) == 6 and all(h[i]['jogos_que_chegaram'] >= h[i + 1]['jogos_que_chegaram'] for i in range(5))
    assert set(r['fases']) == {'início', 'meio', 'fim'}
    assert {o['deck'] for o in r['oponentes']} == {o['name'] for o in ops}
    assert TD.relatorio_texto(r)


def test_oponentes_e_candidatas_escolhidos():
    ops, _ = TD.listar_oponentes(A, nomes=[B, A, 'tests/05_heiremans_crustle'])
    assert sorted(o['name'] for o in ops) == sorted([B, 'tests/05_heiremans_crustle'])   # o próprio deck nunca entra
    ids = TD.ids_de_nomes(['Ultra Bola', 'Night Stretcher'])
    assert [TD.db().get(i).name for i in ids] == ['Ultra Ball', 'Night Stretcher']
    try:
        TD.ids_de_nomes(['Carta Que Nao Existe'])
        assert False
    except ValueError as e:
        assert 'Carta Que Nao Existe' in str(e)
    import random
    base = load_deck(A).cards
    c = TD._candidatos(base, [], [], random.Random(1), 20, set(), somente=ids)
    assert c and all(inn in ids for _, _, inn in c)


def test_versao_salva_em_pasta_temporaria():
    tmp = Path(tempfile.mkdtemp())
    orig = (DB.DECK_DIR, decks.DECK_DIR, TD.DECK_DIR)
    base = load_deck(A)
    nova = list(base.cards)
    nova.remove(nova[-1])
    nova.append(DB.db().resolve('Ultra Ball').id)
    (tmp / 'tests').mkdir()
    (tmp / 'tests' / '01_hedrick_dragapult.txt').write_text((orig[0] / 'tests' / '01_hedrick_dragapult.txt').read_text(encoding='utf-8'),
                                                            encoding='utf-8')
    try:
        DB.DECK_DIR = decks.DECK_DIR = TD.DECK_DIR = tmp
        r1 = TD.salvar_versao(A, nova, {'antes': .5, 'depois': .6})
        r2 = TD.salvar_versao(A, nova)
        assert r1['name'] == 'meus/01_hedrick_dragapult_v2' and r2['name'].endswith('_v3')
        d = load_deck(str(tmp / 'meus' / '01_hedrick_dragapult_v2.txt'))
        assert sorted(d.cards) == sorted(nova) and d.meta['origem'] == A and 'trocas' in d.meta
    finally:
        DB.DECK_DIR, decks.DECK_DIR, TD.DECK_DIR = orig


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'):
            f()
            print('ok', n)
