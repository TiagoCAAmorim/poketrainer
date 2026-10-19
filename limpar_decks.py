"""Limpa decks com cartas fora da rotação (a base só tem as marcas H/I/J do formato Padrão atual).

Um deck é "fora da rotação" quando alguma linha não resolve para uma carta da base.
Por padrão só mostra o que faria (simulação); use --aplicar para executar.

Exemplos:
    python limpar_decks.py                          # simula em decks/limitless/
    python limpar_decks.py --aplicar                # move os decks para decks/_fora_da_rotacao/
    python limpar_decks.py --aplicar --apagar       # apaga em vez de mover
    python limpar_decks.py decks/limitless/553_regional_sydney --detalhes
    python limpar_decks.py decks --max-fora 2       # tolera até 2 cartas diferentes fora da rotação

Decks movidos mantêm o caminho relativo (decks/_fora_da_rotacao/limitless/<torneio>/...). Pastas que começam
com "_" são ignoradas por `list_decks`, então não aparecem mais no gerenciador nem nas simulações.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from ptcg.decks import DECK_DIR, parse_decklist

QUARENTENA = 'decks/_fora_da_rotacao'
ROOT = Path(__file__).resolve().parent


def cartas_fora(path: Path) -> list:
    """Linhas do deck que não existem na base (fora da rotação ou desconhecidas)."""
    _, erros = parse_decklist(path.read_text(encoding='utf-8'), path.stem)
    out = []
    for e in erros:
        # KeyError vem entre aspas: "Carta não encontrada (...): 'Arven OBF 186'"
        out.append(str(e).replace("\\'", "'").strip('\'"').split('): ', 1)[-1].strip('\'"'))
    return out


def _atualizar_index(pasta: Path, removidos: set, dest_pasta: Path | None):
    """Tira do index.json os decks removidos; se a pasta ficou vazia, leva o index junto para a quarentena."""
    idx = pasta / 'index.json'
    if not idx.exists():
        return
    restantes = list(pasta.glob('*.txt'))
    if not restantes:
        if dest_pasta is not None:
            dest_pasta.mkdir(parents=True, exist_ok=True)
            shutil.move(str(idx), dest_pasta / 'index.json')
        else:
            idx.unlink()
        if not any(pasta.iterdir()):
            pasta.rmdir()
        return
    data = json.loads(idx.read_text(encoding='utf-8'))
    data['decks'] = [d for d in data.get('decks', []) if Path(d['file']).name not in removidos]
    idx.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pasta', nargs='?', default=str(DECK_DIR / 'limitless'), help='pasta de decks (recursivo)')
    ap.add_argument('--aplicar', action='store_true', help='executa (sem isso é só simulação)')
    ap.add_argument('--apagar', action='store_true', help='apaga os decks em vez de mover para a quarentena')
    ap.add_argument('--max-fora', type=int, default=0,
                    help='nº máximo de cartas diferentes fora da rotação tolerado (padrão 0)')
    ap.add_argument('--detalhes', action='store_true', help='lista as cartas fora da rotação de cada deck')
    a = ap.parse_args()

    base = Path(a.pasta).resolve()
    quarentena = ROOT / QUARENTENA
    if not base.exists():
        sys.exit(f'Pasta não encontrada: {base}')
    arquivos = [p for p in sorted(base.rglob('*.txt'))
                if not any(part.startswith('_') for part in p.relative_to(DECK_DIR).parts)] \
        if base.is_relative_to(DECK_DIR) else sorted(base.rglob('*.txt'))

    ruins, total = [], len(arquivos)
    for p in arquivos:
        fora = cartas_fora(p)
        if len(set(fora)) > a.max_fora:
            ruins.append((p, fora))

    por_pasta = {}
    for p, fora in ruins:
        por_pasta.setdefault(p.parent, []).append((p, fora))
    for pasta, itens in por_pasta.items():
        todos = len(list(pasta.glob('*.txt'))) == len(itens)
        print(f'{pasta.relative_to(ROOT)}: {len(itens)} deck(s) fora da rotação' + (' (pasta inteira)' if todos else ''))
        if a.detalhes:
            for p, fora in itens:
                print(f'   {p.name}: {len(set(fora))} carta(s) — ' + '; '.join(sorted(set(fora))[:6])
                      + (' ...' if len(set(fora)) > 6 else ''))

    print(f'\n{len(ruins)} de {total} decks fora da rotação; {total - len(ruins)} ficam.')
    if not ruins:
        return
    if not a.aplicar:
        print('Simulação: nada foi alterado. Use --aplicar para ' + ('apagar.' if a.apagar else f'mover para {QUARENTENA}/.'))
        return

    for pasta, itens in por_pasta.items():
        # decks/limitless/<torneio> → decks/_fora_da_rotacao/limitless/<torneio>
        destino = None if a.apagar else quarentena / pasta.relative_to(DECK_DIR)
        for p, _ in itens:
            if destino is None:
                p.unlink()
            else:
                destino.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), destino / p.name)
        _atualizar_index(pasta, {p.name for p, _ in itens}, destino)
    print('Concluído.' + ('' if a.apagar else f' Decks movidos para {QUARENTENA}/.'))
    try:
        from ptcg.logbook import registrar
        registrar('decks', f'limpou {len(ruins)} decks fora da rotação ({"apagados" if a.apagar else "quarentena"})',
                  pasta=str(base))
    except Exception:
        pass


if __name__ == '__main__':
    main()
