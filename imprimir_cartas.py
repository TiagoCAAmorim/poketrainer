"""Gera PDF com as cartas de um deck (ou de uma lista) para imprimir, em escala reduzida/ampliada.

Exemplos:
    python imprimir_cartas.py meus/meu_deck                                  # A4, 90%, com imagens → pdfs/meu_deck.pdf
    python imprimir_cartas.py tests/01_hedrick_dragapult --economico         # layout original em cinza, sem fundos (pouca tinta)
    python imprimir_cartas.py tests/01_hedrick_dragapult --simplificado      # só texto, preto e branco (economiza tinta)
    python imprimir_cartas.py meus/meu_deck --papel Office --escala 85
    python imprimir_cartas.py meus/meu_deck --adicionar "2 Ultra Ball" --remover "1 Boss's Orders" -o saida.pdf
    python imprimir_cartas.py --cartas "4 Dreepy TWM 128" "2 Boss's Orders" --papel 200x300

Papéis: A4 (padrão), Office (Ofício 216×330 mm), A5, Letter, Legal, A3 ou LARGURAxALTURA em mm.
A escala é % do tamanho real da carta (63×88 mm): 90 → 56,7×79,2 mm. Cartas repetidas saem repetidas.
Imagens vêm de `python baixar_imagens.py`; sem imagem a carta sai na versão simplificada.
"""
import argparse
import sys
from pathlib import Path

from ptcg.decks import load_deck, parse_decklist
from ptcg.imprimir import PAPEIS, PAPEL_PADRAO, ajustar, expandir, gerar_pdf, layout

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('deck', nargs='?', help='deck de partida (ex.: meus/meu_deck); opcional se usar --cartas')
    ap.add_argument('--cartas', nargs='*', default=None, help='lista de cartas "N Nome [SET NUM]" (em vez de, ou junto de, um deck)')
    ap.add_argument('--adicionar', nargs='*', default=[], help='cartas a acrescentar, ex.: "2 Ultra Ball"')
    ap.add_argument('--remover', nargs='*', default=[], help='cartas a retirar, ex.: "1 Boss\'s Orders"')
    ap.add_argument('--escala', type=float, default=90, help='%% do tamanho real da carta (padrão 90)')
    ap.add_argument('--papel', default=PAPEL_PADRAO, help=f'{", ".join(PAPEIS)} ou LARGURAxALTURA em mm (padrão {PAPEL_PADRAO})')
    ap.add_argument('--economico', action='store_true', help='mantém o layout e a arte, mas em cinza e sem fundos coloridos (economiza tinta)')
    ap.add_argument('--simplificado', action='store_true', help='cartas só com texto, em preto e branco (sem arte)')
    ap.add_argument('--idioma', choices=['pt', 'en'], default='pt', help='idioma do texto das cartas simplificadas')
    ap.add_argument('--margem', type=float, default=6, help='margem da página em mm (padrão 6)')
    ap.add_argument('--espaco', type=float, default=1, help='espaço entre cartas em mm (padrão 1)')
    ap.add_argument('--orientacao', choices=['auto', 'retrato', 'paisagem'], default='auto')
    ap.add_argument('-o', '--saida', default=None, help='arquivo PDF (padrão: pdfs/<deck>.pdf)')
    a = ap.parse_args()
    if not a.deck and not a.cartas:
        ap.error('informe um deck ou --cartas')
    ids = list(load_deck(a.deck, strict=False).cards) if a.deck else []
    if a.cartas:
        deck, erros = parse_decklist('\n'.join(x if x[:1].isdigit() else '1 ' + x for x in a.cartas))
        if erros:
            sys.exit('\n'.join(erros))
        ids += deck.cards
    try:
        ids = ajustar(ids, a.adicionar, a.remover) if (a.adicionar or a.remover) else expandir({c: ids.count(c) for c in set(ids)})
        nome = (a.deck or 'cartas').replace('/', '_')
        saida = Path(a.saida) if a.saida else ROOT / 'pdfs' / f'{nome}{"_simplificado" if a.simplificado else "_economico" if a.economico else ""}.pdf'
        saida.parent.mkdir(parents=True, exist_ok=True)
        r = gerar_pdf(ids, saida, escala=a.escala / 100, papel=a.papel, simplificado=a.simplificado, economico=a.economico, margem=a.margem,
                      espaco=a.espaco, orientacao=a.orientacao, idioma=a.idioma)
    except ValueError as e:
        sys.exit(f'Erro: {e}')
    print(f'{r["cartas"]} cartas em {r["paginas"]} página(s) ({r["colunas"]}×{r["linhas"]} por página, {r["orientacao"]}), '
          f'cada carta com {r["tamanho_carta_mm"][0]}×{r["tamanho_carta_mm"][1]} mm → {r["arquivo"]}')
    if r['faltando']:
        print(f'Sem imagem (saíram simplificadas; rode baixar_imagens.py): {", ".join(r["faltando"])}')


if __name__ == '__main__':
    main()
