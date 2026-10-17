"""As partidas reais do Pokémon TCG Live em tests/fixtures/ptcgl_logs devem ser reproduzidas inteiras.

    python tests/test_replay.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ptcg.replay.replay import replay_log  # noqa: E402

LOGS = sorted(glob.glob(os.path.join(os.path.dirname(__file__), 'fixtures', 'ptcgl_logs', '*.log')))


def test_logs_replay_fully():
    bad = []
    for f in LOGS:
        rep = replay_log(open(f, encoding='utf-8').read())
        if not rep.finished or rep.divergence or rep.actions_done != rep.actions_total:
            bad.append((os.path.basename(f), rep.actions_done, rep.actions_total, rep.divergence))
    assert not bad, bad


if __name__ == '__main__':
    test_logs_replay_fully()
    print('ok', len(LOGS), 'logs')
