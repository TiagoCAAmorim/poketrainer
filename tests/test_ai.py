"""Pipeline da IA: formato compacto, imitação, rollouts e passo PPO (pulado sem PyTorch).

    python tests/test_ai.py
"""
import os
import random
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np  # noqa: E402

try:
    import torch  # noqa: E402
except ImportError:          # pragma: no cover
    torch = None

from ptcg.agents import HeuristicAgent  # noqa: E402
from ptcg.decks import load_deck  # noqa: E402
from ptcg.encode import encode  # noqa: E402
from ptcg.engine import Game  # noqa: E402

DECKS = ['tests/01_hedrick_dragapult', 'tests/08_spry_basic_box']


def _sample_obs(n=60, seed=3):
    d = [load_deck(x).cards for x in DECKS]
    g = Game(d[0], d[1], seed=seed)
    h = HeuristicAgent(seed=seed)
    obs = []
    while not g.done and len(obs) < n:
        if len(g.prompt.options) > 1:
            obs.append(encode(g))
        g.step(h.act(g, g.prompt))
    return obs


def test_packed_batch_matches_collate():
    if torch is None:
        return
    from ptcg.ai.dataset import ObsPacker, PackedObs
    from ptcg.ai.model import collate
    obs = _sample_obs()
    pk = ObsPacker()
    for i, o in enumerate(obs):
        pk.add(o, action=i % 2, value=0.5)
    pk.truncate(len(obs) - 5)            # descartar o fim (como numa partida com erro) mantém o resto íntegro
    obs = obs[:-5]
    data = PackedObs([pk.arrays({'action': np.int16})])
    assert len(data) == len(obs)
    idx = np.array([3, 0, len(obs) - 1, 10])
    b = data.batch(idx)
    ref = collate([obs[i] for i in idx])
    A = ref['opt_ids'].shape[1]
    assert b['opt_ids'].shape[1] >= A and not b['opt_mask'][:, A:].any()   # preenchimento extra fica mascarado
    for k, v in ref.items():
        got = b[k][:, :A] if k.startswith('opt_') else b[k]
        assert got.shape == tuple(v.shape), (k, got.shape, v.shape)
        assert np.allclose(got, v.numpy(), atol=2e-3), k
    assert list(b['action']) == [i % 2 for i in idx] and np.allclose(b['value'], 0.5)


def test_generate_and_train_imitation():
    if torch is None:
        return
    from ptcg.ai.dataset import PackedObs, generate
    from ptcg.ai.imitate import train_imitation
    with tempfile.TemporaryDirectory() as tmp:
        st = generate(tmp, 4, DECKS, workers=2, games_per_shard=2, log=lambda *_: None)
        assert st['games'] == 4 and st['errors'] == 0 and st['samples'] > 100
        data = PackedObs.from_dir(tmp)
        assert len(data) == st['samples']
        assert set(np.unique(data.d['value'])) <= {-1.0, 0.0, 1.0}
        out = os.path.join(tmp, 'im.pt')
        net = train_imitation(tmp, out, epochs=1, batch=64, hidden=32, emb=8, device='cpu', log=lambda *_: None)
        assert os.path.exists(out)
        assert all(torch.isfinite(p).all() for p in net.parameters())


def test_rollout_and_ppo_step():
    if torch is None:
        return
    from ptcg.ai.dataset import PackedObs
    from ptcg.ai.model import PolicyValueNet, save_checkpoint
    from ptcg.ai.train import ppo_update, rollout_task
    with tempfile.TemporaryDirectory() as tmp:
        net = PolicyValueNet(hidden=32, emb=8)
        path = os.path.join(tmp, 'learner.pt')
        save_checkpoint(path, net)
        cfg = dict(gamma=0.997, lam=0.95, shaping=0.05, p_heuristic=0.5, p_pool=0.0, parallel=2,
                   max_decisions=3000)
        arrays, results, stats = rollout_task((path, [], 2, 1, DECKS, cfg))
        assert stats['errors'] == 0 and arrays is not None
        data = PackedObs([arrays])
        assert {'action', 'logp', 'adv', 'ret'} <= set(data.scalar_keys)
        opt = torch.optim.Adam(net.parameters(), lr=1e-4)
        args = SimpleNamespace(epochs=1, minibatch=256, clip=0.2, vf_coef=0.5, ent_coef=0.01, max_grad=0.5)
        st = ppo_update(net, opt, data, args, 'cpu')
        assert all(np.isfinite(v) for v in st.values()), st
        # logp gravado no rollout bate com a rede antes da atualização? (só confere a faixa)
        assert (data.d['logp'] <= 0).all()


if __name__ == '__main__':
    import traceback
    random.seed(0)
    if torch is None:
        print('PyTorch não instalado: testes da IA pulados')
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            try:
                fn()
                print('ok  ', name)
            except Exception:
                fails += 1
                print('FAIL', name)
                traceback.print_exc()
    print('falhas:', fails)
