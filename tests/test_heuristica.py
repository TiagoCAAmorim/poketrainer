"""IA heurística: precisa continuar vencendo o jogador aleatório (ver melhorar_heuristica.py)."""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ptcg.agents import DEFAULT_PARAMS, load_params
from ptcg.decks import load_deck
from ptcg.sim import run_matchup


def test_params_validos():
    p = load_params()
    assert set(p) == set(DEFAULT_PARAMS)


def test_vence_aleatorio():
    arquivos = sorted(glob.glob('decks/tests/*.txt'))
    total = 0
    for f in arquivos:
        d = load_deck(f).cards
        total += run_matchup(d, d, 40, 'heuristic', 'random', 12345)['winrate']
    media = total / len(arquivos)
    assert media >= 0.85, f'heurística ganha só {100 * media:.1f}% do aleatório'


if __name__ == '__main__':
    falhas = 0
    for nome, fn in list(globals().items()):
        if nome.startswith('test_') and callable(fn):
            try:
                fn()
                print('ok  ', nome)
            except AssertionError as e:
                falhas += 1
                print('FALHA', nome, e)
    print('falhas:', falhas)
    sys.exit(1 if falhas else 0)
