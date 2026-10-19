"""Avisa sobre problemas apontados pelo usuário nas partidas (logs/problemas.jsonl) ainda não corrigidos.

    python tools/problemas_pendentes.py            lista sempre
    python tools/problemas_pendentes.py --sessao   hook SessionStart: só na 1ª sessão de cada dia

A saída do hook entra no contexto do agente. O dia da última vez fica em .claude/.aviso_problemas (gitignore).
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ptcg.logbook import problemas  # noqa: E402

MARCA = ROOT / '.claude' / '.aviso_problemas'


def main():
    sessao = '--sessao' in sys.argv
    hoje = date.today().isoformat()
    if sessao and MARCA.exists() and MARCA.read_text().strip() == hoje:
        return
    abertos = problemas('aberto')
    if sessao:
        MARCA.write_text(hoje)
    if not abertos:
        return
    print(f'PROBLEMAS PENDENTES apontados pelo usuário durante partidas ({len(abertos)} sem correção):')
    for r in abertos:
        print(f'- {r["id"]} ({r["quando"][:10]}, turno {r["turno"]}, {" x ".join(r["jogadores"])}): {r["texto"]}')
    print('\nINSTRUÇÃO: esta é a primeira sessão do dia. Antes de seguir, apresente esta lista ao usuário e PROPONHA '
          'tratar os problemas pendentes (detalhe: `python gerenciar_logs.py problema <ID>`). Ao corrigir um, '
          'rode os testes e marque com `python gerenciar_logs.py corrigir <ID> --nota "..."`. '
          'Não corrija sem o usuário concordar.')


if __name__ == '__main__':
    main()
