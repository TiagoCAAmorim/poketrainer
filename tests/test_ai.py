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


def _sample_obs(n=60, seed=3, versao=1):
    d = [load_deck(x).cards for x in DECKS]
    g = Game(d[0], d[1], seed=seed)
    h = HeuristicAgent(seed=seed)
    obs = []
    while not g.done and len(obs) < n:
        if len(g.prompt.options) > 1:
            obs.append(encode(g, versao=versao))
        g.step(h.act(g, g.prompt))
    return obs


def test_packed_batch_matches_collate(versao=1):
    if torch is None:
        return
    from ptcg.ai.dataset import ObsPacker, PackedObs
    from ptcg.ai.model import collate
    obs = _sample_obs(versao=versao)
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
    assert data.obs == versao and (('deck_ids' in b) == (versao == 2))


def test_v2_formato_e_rede():
    """Observação v2: lote compacto = collate; a rede v2 roda; v1 continua igual (redes antigas)."""
    test_packed_batch_matches_collate(versao=2)
    o1, o2 = _sample_obs(5)[-1], _sample_obs(5, versao=2)[-1]
    assert all(np.array_equal(o1[k], o2[k]) for k in o1)          # v2 só acrescenta campos
    assert o2['deck_cnt'].sum() * 4 > 0 and o2['slot_x'].shape[1] > 0
    if torch is None:
        return
    from ptcg.ai.model import PolicyValueNet, collate
    net = PolicyValueNet(hidden=32, emb=8, obs=2)
    logits, value = net(collate(_sample_obs(8, versao=2)))
    assert logits.shape[0] == 8 and torch.isfinite(value).all()
    assert 'obs' not in PolicyValueNet(hidden=32, emb=8).config   # config v1 inalterada


def test_generate_and_train_imitation(versao=1):
    if torch is None:
        return
    from ptcg.ai.dataset import PackedObs, generate
    from ptcg.ai.imitate import train_imitation
    with tempfile.TemporaryDirectory() as tmp:
        st = generate(tmp, 4, DECKS, workers=2, games_per_shard=2, log=lambda *_: None, versao=versao)
        assert st['games'] == 4 and st['errors'] == 0 and st['samples'] > 100
        data = PackedObs.from_dir(tmp)
        assert len(data) == st['samples']
        assert set(np.unique(data.d['value'])) <= {-1.0, 0.0, 1.0}
        out = os.path.join(tmp, 'im.pt')
        net, resumo = train_imitation(tmp, out, epochs=1, batch=64, hidden=32, emb=8, device='cpu', log=lambda *_: None)
        assert os.path.exists(out) and resumo['melhor_epoca']['epoca'] == 1
        assert all(torch.isfinite(p).all() for p in net.parameters())
        assert net.obs == versao


def test_generate_and_train_imitation_v2():
    test_generate_and_train_imitation(versao=2)


def test_generate_professora_rede():
    """Imitação de uma rede (destilação): a rede v1 ensina e os dados saem na v2; pastas não misturam professoras."""
    if torch is None:
        return
    from ptcg.ai.dataset import generate
    from ptcg.ai.model import PolicyValueNet, save_checkpoint
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'prof.pt')
        save_checkpoint(path, PolicyValueNet(hidden=32, emb=8))
        out = os.path.join(tmp, 'dados')
        st = generate(out, 2, DECKS, workers=1, games_per_shard=2, log=lambda *_: None, versao=2,
                      professor=f'model:{path}')
        assert st['games'] == 2 and st['errors'] == 0 and st['samples'] > 50
        try:
            generate(out, 1, DECKS, workers=1, log=lambda *_: None, versao=2)
            assert False, 'misturou professoras'
        except ValueError:
            pass


def test_rollout_and_ppo_step(versao=1):
    if torch is None:
        return
    from ptcg.ai.dataset import PackedObs
    from ptcg.ai.model import PolicyValueNet, save_checkpoint
    from ptcg.ai.train import ppo_update, rollout_task
    with tempfile.TemporaryDirectory() as tmp:
        net = PolicyValueNet(hidden=32, emb=8, obs=versao)
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
        assert data.obs == versao


def test_rollout_and_ppo_step_v2():
    test_rollout_and_ppo_step(versao=2)


def test_busca_sorteio_e_agente():
    """Busca: o sorteio só mexe nas cartas ocultas (mesmo conjunto, mesmos tamanhos, visíveis e face_up intactas)."""
    from collections import Counter
    from ptcg.ai.busca import pode_buscar, sortear_ocultas
    d = [load_deck(x).cards for x in DECKS]
    g = Game(d[0], d[1], seed=4)
    h = HeuristicAgent(seed=4)
    while not (g.setup_done and g.turn >= 4 and g.prompt.player == 0 and g.prompt.hint == 'main'):
        g.step(h.act(g, g.prompt))
    w = g.clone()
    op, me = w.players[1], w.players[0]
    op.prizes[0].face_up = True
    fixa = op.prizes[0]

    def visiveis(G):
        return [sorted(c.uid for c in p.discard + p.lost_zone + [x for s in p.in_play() for x in s.all_cards()])
                for p in G.players]
    antes = (visiveis(w), [c.uid for c in me.hand], [(len(p.hand), len(p.deck), len(p.prizes)) for p in w.players],
             Counter(c.uid for c in op.hand + op.deck + op.prizes), Counter(c.uid for c in me.deck + me.prizes))
    mao_op = [c.uid for c in op.hand]
    sortear_ocultas(w, 0, random.Random(1))
    depois = (visiveis(w), [c.uid for c in me.hand], [(len(p.hand), len(p.deck), len(p.prizes)) for p in w.players],
              Counter(c.uid for c in op.hand + op.deck + op.prizes), Counter(c.uid for c in me.deck + me.prizes))
    assert antes == depois and op.prizes[0] is fixa and [c.uid for c in op.hand] != mao_op
    assert pode_buscar(g, 0) and not pode_buscar(g, 1)
    if torch is None:
        return
    from ptcg.agents import make_agent
    from ptcg.ai.model import PolicyValueNet, save_checkpoint
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'net.pt')
        save_checkpoint(path, PolicyValueNet(hidden=32, emb=8))
        ag = make_agent(f'busca:model:{path}|mundos=2,candidatos=2,limiar=1.1,horizonte=1', seed=0)
        n = len(g.history)
        assert 0 <= ag.act(g, g.prompt) < len(g.prompt.options) and len(g.history) == n   # não mexe na partida real
        assert ag.stats['buscas'] == 1 and ag.stats['simulacoes'] == 4


def test_niveis_elo_e_exportacao():
    """Elo por máxima verossimilhança recupera as diferenças; níveis de ias/ carregam e jogam."""
    from ptcg.ai import niveis
    regs = [{'tipo': 'avaliacao', 'checkpoint': 'a.pt', 'oponente': 'heuristic', 'vitorias': 0.76, 'partidas': 2000},
            {'tipo': 'avaliacao', 'checkpoint': 'b.pt', 'oponente': 'model:a.pt', 'vitorias': 0.64, 'partidas': 1000}]
    r = niveis.elo(regs)
    assert r['heuristic'] == 0 and abs(r['a.pt'] - 200) < 3 and abs(r['b.pt'] - 300) < 3, r
    assert niveis.carregar()[0]['nivel'] == 0 and niveis.spec(0) == 'heuristic'
    if torch is None:
        return
    from ptcg.agents import make_agent
    from ptcg.ai.model import PolicyValueNet, load_checkpoint, save_checkpoint
    with tempfile.TemporaryDirectory() as tmp:
        net = PolicyValueNet(hidden=32, emb=8)
        src, dst = os.path.join(tmp, 'net.pt'), os.path.join(tmp, 'compacta.pt')
        save_checkpoint(src, net)
        niveis.exportar(src, __import__('pathlib').Path(dst))
        back, extra = load_checkpoint(dst)
        assert extra['origem'] == src
        assert max((p - q).abs().max().item() for p, q in zip(net.parameters(), back.parameters())) < 1e-2
    for n in niveis.carregar()[1:2]:            # o primeiro nível com rede joga uma decisão
        ag = make_agent(f"nivel:{n['nivel']}")
        g = Game(load_deck(DECKS[0]).cards, load_deck(DECKS[1]).cards, seed=1)
        assert 0 <= ag.act(g, g.prompt) < len(g.prompt.options)


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
