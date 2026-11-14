"""Testa UM deck contra todos os outros decks registrados e sugere trocas de cartas.

Exemplos:
    python testar_deck.py meus/meu_deck                         # 20 partidas contra cada deck de decks/
    python testar_deck.py tests/01_hedrick_dragapult --contra tests/,meus/ --partidas 40
    python testar_deck.py meus/meu_deck --maximo 100 --sugerir --salvar     # 100 oponentes sorteados + versão nova
    python testar_deck.py meus/meu_deck --json resultado.json

Relatório: vitórias por ordem de jogo (1º/2º), cartas mais usadas, cartas que menos ajudaram, combos, histograma da
vez do jogador em que cada prêmio saiu, melhores cartas/combos por fase (início/meio/fim) e matchups difíceis.
Com --sugerir, procura trocas (−1 carta, +1 carta) validadas por simulação; --salvar grava a lista nova em
decks/meus/<deck>_vN.txt para novos testes.
"""
import argparse
import json
import sys
import time

from ptcg.logbook import registrar
from ptcg.testdeck import (Pool, listar_oponentes, relatorio_sugestoes, relatorio_texto, salvar_versao, sugerir_trocas,
                           testar_deck)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('deck', help='nome em decks/ (ex.: meus/meu_deck) ou caminho do .txt')
    ap.add_argument('--partidas', type=int, default=20, help='partidas contra cada oponente (padrão 20)')
    ap.add_argument('--contra', default=None, help='filtro por nome do deck oponente, separado por vírgula '
                                                    '(ex.: tests/,meus/ ou dragapult); padrão: todos')
    ap.add_argument('--oponentes', nargs='*', default=None, help='lista exata de decks oponentes (ignora --contra/--maximo)')
    ap.add_argument('--maximo', type=int, default=None, help='sorteia no máximo N oponentes')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--agente', default='heuristic', help="IA dos dois lados: 'heuristic' ou 'model:checkpoints/ppo3/t1/latest.pt' (roda na CPU, nunca na GPU)")
    ap.add_argument('--workers', type=int, default=None, help='processos (padrão: todos os núcleos − 1; use poucos se houver treino rodando)')
    ap.add_argument('--sugerir', action='store_true', help='procura trocas de cartas que melhorem o deck')
    ap.add_argument('--rodadas', type=int, default=3, help='máximo de trocas aceitas (uma por rodada)')
    ap.add_argument('--candidatos', type=int, default=24, help='trocas testadas por rodada')
    ap.add_argument('--candidatas', nargs='*', default=None, help='cartas que podem entrar nas trocas (padrão: automático)')
    ap.add_argument('--travar', nargs='*', default=[], help='nomes de cartas que não devem sair')
    ap.add_argument('--salvar', action='store_true', help='grava a lista sugerida como nova versão em decks/meus/')
    ap.add_argument('--nome', default=None, help='nome da nova versão (padrão: <deck>_vN)')
    ap.add_argument('--json', default=None, help='salva resultados completos em JSON')
    ap.add_argument('--top', type=int, default=10)
    a = ap.parse_args()

    t = time.time()
    ult = [0.0]

    def prog(rot, feitos, total):
        if time.time() - ult[0] > 1 or feitos == total:
            ult[0] = time.time()
            print(f'\r  {rot}: {feitos}/{total}   ', end='', file=sys.stderr, flush=True)

    def ev(msg):
        print(f'\n  · {msg}', file=sys.stderr)

    with Pool(a.workers, a.agente) as pool:
        ops = None
        if a.oponentes:
            ops, _ = listar_oponentes(a.deck, nomes=a.oponentes)
        res = testar_deck(a.deck, a.partidas, a.contra, a.maximo, a.seed, progresso=prog, pool=pool, oponentes=ops, evento=ev)
        print(file=sys.stderr)
        print(relatorio_texto(res, a.top))
        registrar('teste_deck', f'{a.deck}: {res["jogos"]} partidas, {100 * res["winrate"]:.1f}% de vitórias',
                  oponentes=res['n_oponentes'])
        sug = None
        if a.sugerir:
            print('\nProcurando trocas (pode levar alguns minutos)...', file=sys.stderr)
            sug = sugerir_trocas(a.deck, res, candidatos=a.candidatos, rodadas=a.rodadas, progresso=prog,
                                 pool=pool, travadas=a.travar, candidatas=a.candidatas, oponentes=ops, evento=ev)
            print(file=sys.stderr)
            print('\n' + relatorio_sugestoes(sug))
            if a.salvar:
                if sug['mudou']:
                    r = salvar_versao(a.deck, sug['lista'], sug, a.nome)
                    print(f'\nNova versão salva: {r["name"]}  →  python testar_deck.py {r["name"]}')
                else:
                    print('\nNada a salvar: nenhuma troca confirmou.')
        elif a.salvar:
            print('--salvar só faz sentido com --sugerir', file=sys.stderr)
    print(f'\nTotal: {time.time() - t:.0f}s')
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump({'teste': res, 'sugestoes': sug}, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
