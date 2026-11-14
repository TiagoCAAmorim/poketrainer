"""Atualiza as cartas da página estática (site/data/cartas.js) e gera um relatório para conferência.

    python tools/atualizar_cartas_site.py                 # reconstrói a base (clona/atualiza fontes), regera e confere
    python tools/atualizar_cartas_site.py --sem-rede      # reaproveita .cache/cards_site.json (só regera e confere)

Passos: build_carddb (marcas de MARCAS) → build_pt_texts → build_site → tests/test_site.py.
Escreve `.cache/relatorio_cartas_site.md` (comparação com a versão anterior, cartas sem texto em português,
decks com carta desconhecida) para a pessoa ou a IA seguir o roteiro em docs/ROTEIRO_CARTAS_SITE.md.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / '.cache'
DADOS = RAIZ / 'site' / 'data' / 'cartas.js'
MARCAS = 'G,H,I,J'   # marcas de regulação cobertas pelas temporadas do site; acrescente a nova quando sair coleção com marca nova
RELATORIO = CACHE / 'relatorio_cartas_site.md'


def rodar(*cmd):
    print('$', ' '.join(cmd), flush=True)
    return subprocess.run([sys.executable, *cmd], cwd=RAIZ).returncode


def ler(path):
    txt = Path(path).read_text(encoding='utf-8')
    return json.loads(txt[txt.index('=') + 1:].rstrip(';'))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sem-rede', action='store_true')
    a = ap.parse_args()
    antes = ler(DADOS) if DADOS.exists() else {'cartas': {}, 'impressoes': {}}
    if not a.sem_rede:
        for cmd in (('tools/build_carddb.py', '--marks', MARCAS, '--out', '.cache/cards_site.json'),
                    ('tools/build_pt_texts.py', '--cards', '.cache/cards_site.json', '--out', '.cache/cards_pt_site.json')):
            if rodar(*cmd):
                sys.exit('Falhou: ' + ' '.join(cmd))
    if rodar('tools/build_site.py'):
        sys.exit('Falhou: tools/build_site.py')
    depois = ler(DADOS)
    sets = lambda d: {k.rsplit('-', 1)[0] for k in d['impressoes']}   # noqa: E731
    novas = sorted(set(depois['cartas']) - set(antes['cartas']))
    sumiram = sorted(set(antes['cartas']) - set(depois['cartas']))
    sem_pt = sorted(c['n'] for c in depois['cartas'].values() if not c.get('p') and c['k'] == 'p' and c['en'] == c['pt'])
    mudaram = sorted(c for c in set(antes['cartas']) & set(depois['cartas']) if antes['cartas'][c] != depois['cartas'][c])
    linhas = ['# Relatório — cartas do site', '',
              f'- Cartas: {len(antes["cartas"])} → {len(depois["cartas"])}  (novas {len(novas)}, sumiram {len(sumiram)}, alteradas {len(mudaram)})',
              f'- Coleções novas: {", ".join(sorted(sets(depois) - sets(antes))) or "nenhuma"}',
              f'- Pokémon sem tradução (texto igual ao inglês): {len(sem_pt)}', '']
    for titulo, ids in (('Novas', novas), ('Sumiram (conferir: rotação ou erro?)', sumiram), ('Alteradas (errata / texto)', mudaram)):
        linhas += [f'## {titulo} ({len(ids)})', *[f'- {i} {(depois["cartas"].get(i) or antes["cartas"].get(i))["n"]}' for i in ids[:60]],
                   '...' if len(ids) > 60 else '', '']
    teste = rodar('tests/test_site.py')
    linhas.append(f'## tests/test_site.py: {"OK" if teste == 0 else "FALHOU (veja a saída; provável carta de deck não encontrada)"}')
    CACHE.mkdir(exist_ok=True)
    RELATORIO.write_text('\n'.join(linhas) + '\n', encoding='utf-8')
    print(f'\nRelatório: {RELATORIO}')
    sys.exit(teste)


if __name__ == '__main__':
    main()
