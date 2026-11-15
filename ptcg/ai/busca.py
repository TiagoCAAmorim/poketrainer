"""Busca na hora de jogar: antes de uma decisão difícil, simula as jogadas candidatas em "mundos" sorteados.

A rede decide sozinha quando está confiante (probabilidade da melhor opção ≥ `limiar`). Senão:

1. **Candidatas**: as `candidatos` opções mais prováveis segundo a rede.
2. **Mundos**: cópias da partida (Game.clone) em que as **cartas ocultas são sorteadas de novo**, respeitando o que o
   jogador sabe. Do oponente, o que pode estar na mão, no deck e nos Prêmios é a lista dele **menos as cartas já vistas**
   (em jogo, no descarte, na Lost Zone, Estádio, cartas reveladas `face_up`). As cartas dele são embaralhadas entre mão,
   deck e Prêmios, mantendo o tamanho de cada zona. Do próprio jogador, a mão é conhecida e deck e Prêmios
   são embaralhados juntos (ele não sabe quais cartas estão nos Prêmios). O acaso futuro (moedas, compras) também muda.
3. **Simulação**: em cada mundo, joga a candidata e continua com a própria rede (gulosa) para os dois lados até
   `horizonte` turnos depois (2 = fim do turno do oponente, início do meu próximo) ou o fim da partida; o resultado é
   o valor estimado pela rede (ou ±1 se a partida acabou), do ponto de vista de quem decide.
4. Escolhe a candidata com a melhor média (os mesmos mundos para todas as candidatas → comparação justa).

Suposição: a lista do oponente é conhecida (como em torneio, em que as listas do metagame são públicas); a ordem e
quais cartas estão em cada zona oculta, não.

Uso: `make_agent('busca:nivel:9')`, `make_agent('busca:nivel:9|mundos=16,candidatos=4')`;
avaliação: `python ia.py busca --oponente nivel:9 --partidas 400`.
"""
from __future__ import annotations

import math
import os
import random
import time
from multiprocessing import get_context

import numpy as np

from ..agents import Agent
from ..core import Card

PADRAO = dict(mundos=8, candidatos=3, limiar=0.9, horizonte=2, max_passos=120, min_prob=0.02)


# ------------------------------------------------------------------ sorteio das cartas ocultas
def sortear_ocultas(g, eu: int, rng: random.Random):
    """Redistribui as cartas que `eu` não vê, mantendo o tamanho de cada zona (altera `g`).

    Oponente: mão + deck + Prêmios embaralhados entre si (o conjunto = lista dele − cartas vistas).
    Eu: deck + Prêmios embaralhados entre si (a minha mão eu conheço). Cartas `face_up` ficam onde estão."""
    op = g.players[1 - eu]
    _embaralhar_zonas(rng, [op.hand, op.deck, op.prizes])
    me = g.players[eu]
    _embaralhar_zonas(rng, [me.deck, me.prizes])


def _embaralhar_zonas(rng, zonas):
    ocultas = [c for z in zonas for c in z if not c.face_up]
    rng.shuffle(ocultas)
    it = iter(ocultas)
    for z in zonas:
        z[:] = [c if c.face_up else next(it) for c in z]     # mesma lista (o motor guarda referências)


def _cartas(v):
    if isinstance(v, Card):
        yield v
    elif isinstance(v, (list, tuple, set, frozenset)):
        for x in v:
            yield from _cartas(x)


def pode_buscar(g, eu: int) -> bool:
    """Só busca quando nenhuma opção aponta para uma carta oculta (ex.: escolher do deck), pois o sorteio a moveria."""
    pr = g.prompt
    if pr is None or not g.setup_done or pr.player != eu:
        return False
    ocultas = {c.uid for z in (g.players[eu].deck, g.players[eu].prizes, g.players[1 - eu].hand,
                               g.players[1 - eu].deck, g.players[1 - eu].prizes) for c in z}
    return not any(c.uid in ocultas for o in pr.options for c in _cartas(o.value))


# ------------------------------------------------------------------ agente
class BuscaAgent(Agent):
    name = 'busca'

    def __init__(self, base: str, seed=None, **opcoes):
        from ..agents import make_agent
        self.base = make_agent(base)                 # TorchAgent (gulosa)
        if not hasattr(self.base, 'evaluate'):
            raise ValueError(f'a busca precisa de uma rede (model:… ou nivel:N com rede), recebeu {base!r}')
        self.op = {**PADRAO, **opcoes}
        self.rng = random.Random(seed)
        self.stats = {'decisoes': 0, 'buscas': 0, 'mudou': 0, 'simulacoes': 0, 'mundos_com_erro': 0, 's': 0.0}
        self.erros: list[str] = []

    def act(self, g, prompt):
        probs, _ = self.base.evaluate(g, prompt)
        self.stats['decisoes'] += 1
        ordem = [int(i) for i in np.argsort(-probs)]
        melhor = ordem[0]
        if probs[melhor] >= self.op['limiar'] or not pode_buscar(g, prompt.player):
            return melhor
        cands = [i for i in ordem[:self.op['candidatos']] if probs[i] >= self.op['min_prob']]
        if len(cands) < 2:
            return melhor
        t0 = time.perf_counter()
        notas = self.avaliar_candidatas(g, prompt.player, cands)
        escolha = max(cands, key=lambda i: (notas[i], probs[i]))
        self.stats['buscas'] += 1
        self.stats['mudou'] += escolha != melhor
        self.stats['s'] += time.perf_counter() - t0
        return escolha

    def avaliar_candidatas(self, g, eu, cands) -> dict:
        """Média por candidata nos mesmos mundos; um mundo em que o motor falha (estado sorteado que um efeito não
        aceita) é descartado para todas as candidatas, para a comparação continuar justa."""
        soma = {a: 0.0 for a in cands}
        n = 0
        for _ in range(self.op['mundos']):
            semente = self.rng.randrange(2 ** 31)
            notas = {}
            try:
                for a in cands:
                    w = g.clone()
                    sortear_ocultas(w, eu, random.Random(semente))
                    w.rng = random.Random(semente + 1)       # acaso futuro do mundo (igual para todas as candidatas)
                    w.step(a)
                    notas[a] = self.simular(w, eu, g.turn)
                    self.stats['simulacoes'] += 1
            except Exception as e:                           # noqa: BLE001
                self.stats['mundos_com_erro'] += 1
                if len(self.erros) < 20:
                    import traceback
                    onde = ' < '.join(f'{os.path.basename(f.filename)}:{f.lineno} {f.name}'
                                      for f in reversed(traceback.extract_tb(e.__traceback__)[-4:]))
                    self.erros.append(f'{type(e).__name__}: {e} @ {onde}'[:400])
                continue
            for a, v in notas.items():
                soma[a] += v
            n += 1
        return {a: s / max(1, n) for a, s in soma.items()}

    def simular(self, w, eu, turno0) -> float:
        """Continua com a rede para os dois lados até o horizonte; valor do ponto de vista de `eu`."""
        net = self.base
        for _ in range(self.op['max_passos']):
            if w.done:
                return 0.0 if w.winner in (-1, None) else (1.0 if w.winner == eu else -1.0)
            if w.turn >= turno0 + self.op['horizonte']:
                break
            probs, _ = net.evaluate(w, w.prompt)
            w.step(int(probs.argmax()))
        if w.done:
            return 0.0 if w.winner in (-1, None) else (1.0 if w.winner == eu else -1.0)
        _, v = net.evaluate(w, w.prompt)
        return v if w.prompt.player == eu else -v


def criar(spec: str, seed=None) -> BuscaAgent:
    """'busca:<agente base>[|chave=valor,...]', ex.: 'busca:nivel:9|mundos=16,limiar=0.8'."""
    corpo = spec.split(':', 1)[1]
    base, _, resto = corpo.partition('|')
    opcoes = {}
    for par in filter(None, resto.split(',')):
        k, v = par.split('=')
        opcoes[k.strip()] = type(PADRAO[k.strip()])(float(v)) if k.strip() in PADRAO else v
    return BuscaAgent(base, seed=seed, **opcoes)


# ------------------------------------------------------------------ avaliação em paralelo
def _jogar(task):
    import torch
    torch.set_num_threads(1)
    from ..agents import make_agent
    from ..decks import load_deck
    from ..engine import Game
    spec, oponente, jogos, deck_names, max_decisions = task
    ag = make_agent(spec)
    opp = make_agent(oponente)
    decks, res, erros = {}, [], []
    for seed, me in jogos:                  # mesmo sorteio de confrontos de imitate.evaluate_parallel
        rng = random.Random(seed)
        names = (rng.choice(deck_names), rng.choice(deck_names))
        for n in names:
            if n not in decks:
                decks[n] = load_deck(n).cards
        try:
            g = Game(decks[names[0]], decks[names[1]], seed=rng.randrange(2 ** 31))
            while not g.done and g.decisions < max_decisions:
                a = ag if g.prompt.player == me else opp
                g.step(a.act(g, g.prompt))
        except Exception as e:                               # noqa: BLE001  (erro do motor: partida descartada)
            erros.append(f'{names}: {type(e).__name__}: {e}'[:300])
            continue
        score = 1.0 if g.winner == me else (0.5 if g.winner in (-1, None) else 0.0)
        res.append({'deck': names[me], 'score': score, 'primeiro': g.first_player == me})
    st = dict(getattr(ag, 'stats', {}))
    st['partidas_com_erro'] = len(erros)
    return res, st, erros + getattr(ag, 'erros', [])


def avaliar(spec: str, oponente='heuristic', n_games=200, seed=777, workers=None, deck_names=None,
            max_decisions=3000) -> dict:
    """Taxa de vitória de `spec` (qualquer agente de make_agent, ex.: 'busca:nivel:9') contra `oponente`."""
    from ..decks import list_decks
    deck_names = deck_names or list_decks()
    workers = workers or max(1, min((os.cpu_count() or 2) - 2, n_games))
    jogos = [(seed + k, k % 2) for k in range(n_games)]
    tasks = [(spec, oponente, jogos[i::workers], deck_names, max_decisions) for i in range(workers) if jogos[i::workers]]
    t0 = time.perf_counter()
    with get_context('spawn').Pool(len(tasks)) as pool:
        partes = pool.map(_jogar, tasks)
    res = [r for p, _, _ in partes for r in p]
    st = {}
    for _, s, _ in partes:
        for k, v in s.items():
            st[k] = st.get(k, 0) + v
    erros = [e for _, _, es in partes for e in es]
    sc = [r['score'] for r in res]
    first = [r['score'] for r in res if r['primeiro']]
    out = {'oponente': oponente, 'partidas': len(res), 'vitorias': round(float(np.mean(sc)), 3),
           'indo_primeiro': round(float(np.mean(first)), 3) if first else None,
           'erro_padrao': round(float(np.std(sc) / math.sqrt(len(sc))), 3), 's': round(time.perf_counter() - t0, 1)}
    if st.get('decisoes'):
        out['busca'] = {'buscas_por_decisao': round(st['buscas'] / st['decisoes'], 3),
                        'mudou_por_busca': round(st['mudou'] / max(1, st['buscas']), 3),
                        's_por_busca': round(st['s'] / max(1, st['buscas']), 2),
                        'mundos_com_erro': st.get('mundos_com_erro', 0)}
    if st.get('partidas_com_erro'):
        out['partidas_com_erro'] = st['partidas_com_erro']
    if erros:
        out['erros'] = erros[:5]
    return out
