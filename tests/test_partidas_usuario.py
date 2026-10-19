"""Partidas jogadas na interface SEM comentários de problema viram teste do motor.

Fontes: logs/interface/partidas.jsonl (local) e tests/fixtures/partidas/*.jsonl (versionadas, criadas com
`python gerenciar_logs.py fixar`). Cada partida é refeita (decks + semente + decisões) com as invariantes
checadas a cada decisão, e o resultado precisa ser igual ao gravado. Partidas com comentário (ver
logs/problemas.jsonl) ficam de fora: o usuário apontou erro nelas.

Rodar:  python tests/test_partidas_usuario.py   ou   python -m pytest -q tests/test_partidas_usuario.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ptcg.engine import Game  # noqa: E402
from ptcg.logbook import LOG_DIR, ler_jsonl  # noqa: E402
from tests.fuzz import check as check_invariants  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures', 'partidas')


def partidas_sem_comentarios():
    fontes = sorted(glob.glob(os.path.join(FIXTURES, '*.jsonl'))) + [str(LOG_DIR / 'interface' / 'partidas.jsonl')]
    vistos, out = set(), []
    for f in fontes:
        for rec in ler_jsonl(f):
            chave = (rec.get('semente'), tuple(rec.get('history', ())))
            if rec.get('comentarios') or chave in vistos or not rec.get('history'):
                continue
            vistos.add(chave)
            rec['_fixture'] = f.startswith(FIXTURES)
            out.append(rec)
    return out


def refazer(rec):
    g = Game(rec['decks_ids'][0], rec['decks_ids'][1], seed=rec['semente'], names=rec['jogadores'])
    for k, i in enumerate(rec['history']):
        check_invariants(g)
        assert not g.done and i < len(g.prompt.options), f'decisão {k}: história não cabe mais no motor'
        g.step(i)
    check_invariants(g)
    return g


def test_partidas_do_usuario():
    for rec in partidas_sem_comentarios():
        try:
            g = refazer(rec)
        except AssertionError as e:
            if rec['_fixture'] or 'história não cabe' not in str(e):
                raise
            # gravação local feita antes de uma correção de regras: as decisões não valem mais
            print(f'AVISO: partida local {rec["quando"]} obsoleta (regras mudaram desde a gravação): {e}')
            continue
        assert g.done and g.winner == rec['vencedor'] and g.turn == rec['turnos'], \
            f'{rec["jogadores"]} semente={rec["semente"]}: resultado diferente do gravado'


if __name__ == '__main__':
    recs = partidas_sem_comentarios()
    test_partidas_do_usuario()
    print(f'OK — {len(recs)} partidas do usuário refeitas')
