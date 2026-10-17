"""Reproduz no motor partidas exportadas do Pokémon TCG Live ("Copy Log" no histórico da partida).

Cada jogada do log é refeita pelo motor: o resultado mostra quantas ações foram reproduzidas,
se os danos batem com o log oficial e onde (se em algum ponto) as regras divergiram.

Exemplos:
    python replay_log.py tests/fixtures/ptcgl_logs/*.log
    python replay_log.py minha_partida.txt --verbose
    python replay_log.py logs/*.txt --record dados/imitacao.pkl     # amostras (estado, jogada) p/ IA
"""
import argparse
import glob
import pickle
import sys

from ptcg.replay.replay import replay_log


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('logs', nargs='+', help='arquivos de texto com o log copiado do TCG Live (en ou pt-BR)')
    ap.add_argument('--verbose', action='store_true', help='mostra o log do motor da partida reproduzida')
    ap.add_argument('--record', default=None,
                    help='salva amostras (observação codificada, opção escolhida, jogador) para imitação')
    a = ap.parse_args()
    files = [f for pat in a.logs for f in (glob.glob(pat) or [pat])]
    samples, ok = [], 0
    for f in files:
        with open(f, encoding='utf-8') as fh:
            text = fh.read()
        print(f'=== {f}')
        try:
            rep = replay_log(text, record=bool(a.record))
        except Exception as e:      # log ilegível / formato desconhecido
            print(f'  erro: {type(e).__name__}: {e}')
            continue
        print('  ' + rep.summary().replace('\n', '\n  '))
        if a.verbose and rep.game is not None:
            for x in rep.game.log:
                print('    ', x['msg'])
        ok += rep.finished and not rep.divergence
        samples += [(obs, i, p, f) for obs, i, p in rep.samples]
    print(f'\n{ok}/{len(files)} partidas reproduzidas até o fim sem divergência.')
    if a.record:
        with open(a.record, 'wb') as fh:
            pickle.dump(samples, fh)
        print(f'{len(samples)} amostras de decisão salvas em {a.record}')
    return 0 if ok == len(files) else 1


if __name__ == '__main__':
    sys.exit(main())
