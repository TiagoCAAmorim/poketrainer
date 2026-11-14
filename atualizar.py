"""Atualiza o programa (código, redes em ias/ e dados oficiais) a partir do GitHub, sem mexer nos seus decks/logs.

    python atualizar.py            # verifica e pergunta
    python atualizar.py --sim      # atualiza sem perguntar
    python atualizar.py --verificar  # só diz se há versão nova

Na interface, o mesmo está na página inicial (aviso "Nova versão disponível").
"""
import argparse
import sys

from ptcg import atualizar as A


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sim', action='store_true', help='não perguntar')
    ap.add_argument('--verificar', action='store_true', help='só verificar')
    a = ap.parse_args()
    try:
        v = A.verificar()
        print(f"Modo: {v['modo']}")
        if v['aviso']:
            print(v['aviso'])
        if not v['disponivel']:
            print('Você já está na versão mais recente.')
            return 0
        print('Há versão nova:')
        for n in v['novidades']:
            print('  ', n)
        if a.verificar:
            return 0
        if not v['pode_atualizar']:
            return 1
        if not a.sim and input('Atualizar agora? [s/N] ').strip().lower() not in ('s', 'sim', 'y'):
            return 0
        r = A.aplicar()
        print(r['resumo'])
        if r['dependencias']:
            print(A.pip_install())
        print('Pronto. Se o servidor estiver aberto, reinicie-o.')
        return 0
    except A.ErroAtualizacao as e:
        print('Erro:', e)
        return 1


if __name__ == '__main__':
    sys.exit(main())
