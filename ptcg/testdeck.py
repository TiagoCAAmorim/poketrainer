"""Teste de um deck contra todos os outros decks da base + sugestões de troca de cartas.

    from ptcg.testdeck import testar_deck, sugerir_trocas, salvar_versao
    res = testar_deck('meus/meu_deck', partidas=20)           # estatísticas completas (dict JSON-serializável)
    sug = sugerir_trocas('meus/meu_deck', res)                 # trocas validadas por simulação
    salvar_versao('meus/meu_deck', sug['lista'], sug)          # grava meus/meu_deck_v2.txt

Como funciona
  * Cada oponente joga `partidas` partidas contra o deck testado (assentos alternados; quem começa sai da moeda
    do motor), com a IA heurística nos dois lados. O motor registra cada jogada (`Game.plays`) e cada prêmio
    (`Game.prize_turns`) com o número da VEZ do jogador (cada jogador conta uma vez por rodada).
  * As estatísticas são correlações observadas nas partidas simuladas — com poucas partidas por carta/combo elas
    são ruidosas; por isso as listas usam encolhimento (shrinkage) e um mínimo de ocorrências.
  * As sugestões NÃO saem só das correlações: cada troca candidata é jogada contra um "gauntlet" (os confrontos mais
    difíceis + uma amostra aleatória) com as mesmas sementes e só é aceita se confirmar com sementes novas
    contra outro conjunto de oponentes.
"""
from __future__ import annotations

import math
import multiprocessing as mp
import os
import random
import statistics
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from .carddb import db
from .decks import DECK_DIR, list_decks, load_deck, pool_de_cartas, validate

FASES = (('início', 1, 3), ('meio', 4, 7), ('fim', 8, 10 ** 6))   # vezes de cada jogador
K_ENCOLHE = 10          # peso da média geral no encolhimento (equivale a 10 partidas "médias")
CAP_HIST = 20           # vezes acima disso entram no último balde do histograma


# =============================================================== oponentes
def listar_oponentes(deck_nome: str, filtro: str | None = None, maximo: int | None = None, seed: int = 0,
                     nomes: list | None = None):
    """Decks registrados (menos o testado, cópias idênticas e versões derivadas dele).

    nomes: lista exata de decks a usar (tem prioridade sobre filtro/maximo).
    filtro: vírgula = alternativas; cada termo é substring do nome (ex.: 'tests/,meus/' ou 'dragapult').
    Retorna (lista de {'name','cards','arquetipo'}, ignorados [(nome, motivo)])."""
    base = load_deck(deck_nome, strict=False)
    base_key = tuple(sorted(base.cards))
    base_name = deck_nome.replace('\\', '/')
    termos = [t.strip().lower() for t in (filtro or '').split(',') if t.strip()]
    out, ign = [], []
    for n in list_decks():
        if n == base_name or n.endswith(base_name):
            continue
        if nomes is not None and n not in nomes:
            continue
        if nomes is None and termos and not any(t in n.lower() for t in termos):
            continue
        try:
            d = load_deck(n, strict=False)
        except Exception as e:                                   # noqa: BLE001
            ign.append((n, f'não leu: {e}'))
            continue
        if d.meta['errors']:
            ign.append((n, d.meta['errors'][0]))
            continue
        if d.meta.get('origem') in (base_name, base_name.split('/')[-1]):
            continue
        if tuple(sorted(d.cards)) == base_key:
            continue
        out.append({'name': n, 'cards': d.cards,
                    'arquetipo': d.meta.get('archetype') or n.split('/')[-1]})
    if nomes is None and maximo and len(out) > maximo:
        out = random.Random(seed).sample(out, maximo)
        out.sort(key=lambda o: o['name'])
    return out, ign


# =============================================================== execução (processos)
def _resumo(g, me: int, instrumentar: bool) -> dict:
    out = {'res': 0.5 if g.winner == -1 else (1.0 if g.winner == me else 0.0),
           'first': g.first_player == me, 'turns': g.turn, 'reason': g.end_reason,
           'prizes_me': g.prizes_taken(me), 'prizes_opp': g.prizes_taken(1 - me)}
    if not instrumentar:
        return out
    pl = g.players[me]
    seen, hand = Counter(), Counter()
    in_deck_or_prize = Counter(c.name for c in pl.deck) + Counter(c.name for c in pl.prizes)
    for c in pl.hand:
        hand[c.name] += 1
    total = Counter(db().get(cid).name for cid in g.deck_lists[me])
    for nm, n in total.items():
        seen[nm] = n - in_deck_or_prize.get(nm, 0)
    out['plays'] = [(t, k, c, d) for (t, p, k, c, d) in g.plays if p == me]
    out['seen'] = {k: v for k, v in seen.items() if v}
    out['hand'] = dict(hand)
    out['ptp_me'] = [t for (t, p, n) in g.prize_turns if p == me for _ in range(n)]
    out['ptp_opp'] = [t for (t, p, n) in g.prize_turns if p != me for _ in range(n)]
    out['mulligans'] = pl.mulligans
    return out


_AG_CACHE: dict = {}


def _iniciar_worker():
    """Processos de simulação nunca tocam a GPU (a rede roda na CPU, 1 thread) — ela pode estar em treino."""
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ.setdefault('OMP_NUM_THREADS', '1')
    try:
        import torch
        torch.set_num_threads(1)
    except ImportError:
        pass
    try:
        os.nice(10)         # não disputar CPU com treinos em andamento
    except OSError:
        pass


def _agente(spec, seed):
    if spec.startswith('model:'):       # rede: carrega uma vez por processo (é sem estado)
        if spec not in _AG_CACHE:
            from .agents import make_agent
            _AG_CACHE[spec] = make_agent(spec)
        return _AG_CACHE[spec]
    from .agents import make_agent
    return make_agent(spec, seed=seed)


def _lote(job):
    """Joga as partidas de UM oponente. job = (cards, opp_cards, [(seed, seat)], instrumentar, spec)."""
    from .agents import play_game
    cards, opp, partidas, instrumentar, spec = job
    res = []
    for seed, seat in partidas:
        decks = (cards, opp) if seat == 0 else (opp, cards)
        agents = [_agente(spec, seed * 2 + 1), _agente(spec, seed * 2 + 2)]
        g = play_game(decks[0], decks[1], agents, seed=seed)
        res.append(_resumo(g, seat, instrumentar))
    return res


class Pool:
    """Pool de processos reutilizável (spawn: seguro dentro do servidor com threads)."""

    def __init__(self, workers: int | None = None, agente: str = 'heuristic'):
        self.agente = agente
        self.n = workers or max(1, (os.cpu_count() or 2) - 1)
        self.ex = ProcessPoolExecutor(self.n, mp_context=mp.get_context('spawn'), initializer=_iniciar_worker)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.ex.shutdown(wait=False, cancel_futures=True)

    def rodar(self, cards, oponentes, partidas, seed0, instrumentar=False, spec=None, progresso=None,
              rotulo=''):
        """Retorna {nome_oponente: [resumos]} (um lote por oponente, em paralelo)."""
        return self.rodar_varios([cards], oponentes, partidas, seed0, instrumentar, spec, progresso, rotulo)[0]

    def rodar_varios(self, listas, oponentes, partidas, seed0, instrumentar=False, spec=None,
                     progresso=None, rotulo=''):
        """Como `rodar`, para várias listas de uma vez (melhor uso dos processos). Mesmas sementes para todas."""
        spec = spec or self.agente
        futs = {}
        for li, cards in enumerate(listas):
            for i, o in enumerate(oponentes):
                base = seed0 + i * 1000
                jobs = [(base + j, j % 2) for j in range(partidas)]
                futs[self.ex.submit(_lote, (cards, o['cards'], jobs, instrumentar, spec))] = (li, o['name'])
        out, feitos = [{} for _ in listas], 0
        for f in as_completed(futs):
            li, nome = futs[f]
            out[li][nome] = f.result()
            feitos += 1
            if progresso:
                progresso(rotulo, feitos, len(futs))
        return out


# =============================================================== agregação
def _sh(w, n, base, k=K_ENCOLHE):
    return (w + k * base) / (n + k)


def _ic(p, n):
    return 1.96 * math.sqrt(max(p * (1 - p), 1e-9) / n) if n else 0.0


def _fase(t):
    for nome, a, b in FASES:
        if a <= t <= b:
            return nome
    return FASES[-1][0]


def _rotulo(card, detalhe):
    return f'{card} ▸ {detalhe}' if detalhe else card


class Agregador:
    def __init__(self, cards):
        D = db()
        self.cards = list(cards)
        self.copias = Counter(D.get(c).name for c in cards)
        self.kind = {D.get(c).name: D.get(c).kind for c in cards}
        self.basic_energy = {D.get(c).name for c in cards if D.get(c).basic_energy}
        self.n = 0
        self.w = 0.0
        self.first = [0, 0.0]
        self.second = [0, 0.0]
        self.opp = defaultdict(lambda: {'n': 0, 'w': 0.0, 'f': [0, 0.0], 's': [0, 0.0], 'turns': 0,
                                        'pm': 0, 'po': 0})
        self.usos = Counter()                     # (carta) → total de jogadas
        self.por_carta = defaultdict(lambda: Counter())   # carta → contadores
        self.fase_usos = {f[0]: Counter() for f in FASES}
        self.fase_carta = {f[0]: defaultdict(lambda: [0, 0.0]) for f in FASES}   # fase → carta → [n, vitórias]
        self.combos = {f[0]: defaultdict(lambda: [0, 0.0]) for f in FASES}
        self.combos['jogo'] = defaultdict(lambda: [0, 0.0])
        self.prem_me = [Counter() for _ in range(6)]
        self.prem_opp = [Counter() for _ in range(6)]
        self.fim_motivos = Counter()
        self.mull = 0

    def add(self, oname, r):
        res = r['res']
        self.n += 1
        self.w += res
        (self.first if r['first'] else self.second)[0] += 1
        (self.first if r['first'] else self.second)[1] += res
        o = self.opp[oname]
        o['n'] += 1
        o['w'] += res
        o['f' if r['first'] else 's'][0] += 1
        o['f' if r['first'] else 's'][1] += res
        o['turns'] += r['turns']
        o['pm'] += r['prizes_me']
        o['po'] += r['prizes_opp']
        self.fim_motivos[r['reason']] += 1
        self.mull += r.get('mulligans', 0)
        for k, t in enumerate(r['ptp_me']):
            self.prem_me[min(k, 5)][min(t, CAP_HIST)] += 1
        for k, t in enumerate(r['ptp_opp']):
            self.prem_opp[min(k, 5)][min(t, CAP_HIST)] += 1
        usadas, usadas_fase = set(), defaultdict(set)
        por_vez = defaultdict(set)
        for (t, kind, card, det) in r['plays']:
            self.usos[card] += 1
            usadas.add(card)
            f = _fase(t)
            usadas_fase[f].add(card)
            self.fase_usos[f][card] += 1
            if kind == 'ataque' or (kind == 'energia' and card in self.basic_energy):
                continue      # atacar/ligar energia básica aparece em quase toda vez e só "contaminaria" os combos
            por_vez[t].add(_rotulo(card, det) if kind == 'habilidade' else card)
        for nm, n_vistas in r['seen'].items():
            c = self.por_carta[nm]
            c['vista'] += 1
            c['vista_w'] += res
        for nm, n_mao in r['hand'].items():
            self.por_carta[nm]['mao_fim'] += n_mao
        for nm in self.copias:
            c = self.por_carta[nm]
            c['jogos'] += 1
            c['jogos_w'] += res
            if nm in usadas:
                c['usada'] += 1
                c['usada_w'] += res
            if nm in r['seen']:
                c['usada_dado_vista'] += nm in usadas
        for f, nomes in usadas_fase.items():
            for nm in nomes:
                x = self.fase_carta[f][nm]
                x[0] += 1
                x[1] += res
        pares_fase = defaultdict(set)
        for t, labs in por_vez.items():
            ls = sorted(labs)
            f = _fase(t)
            for i in range(len(ls)):
                for j in range(i + 1, len(ls)):
                    pares_fase[f].add((ls[i], ls[j]))
        tudo = set()
        for f, ps in pares_fase.items():
            tudo |= ps
            for p in ps:
                x = self.combos[f][p]
                x[0] += 1
                x[1] += res
        for p in tudo:
            x = self.combos['jogo'][p]
            x[0] += 1
            x[1] += res

    # ---------------------------------------------------------------- resultado
    def resultado(self, oponentes_meta: dict, partidas: int):
        base = self.w / self.n if self.n else 0.5
        min_n = max(8, int(0.02 * self.n))
        return {
            'jogos': self.n, 'winrate': base, 'ic95': _ic(base, self.n),
            'ordem': self._ordem(base),
            'cartas': self._cartas(base, min_n),
            'fases': self._fases(base, min_n),
            'combos': self._combos(base, min_n),
            'premios': {'meu': self._hist(self.prem_me), 'oponente': self._hist(self.prem_opp)},
            'oponentes': self._oponentes(oponentes_meta),
            'arquetipos': self._arquetipos(oponentes_meta),
            'motivos_fim': dict(self.fim_motivos),
        }

    def _ordem(self, base):
        def lin(a):
            n, w = a
            p = w / n if n else float('nan')
            return {'jogos': n, 'winrate': p, 'ic95': _ic(p, n) if n else 0.0}
        d = {'primeiro': lin(self.first), 'segundo': lin(self.second)}
        d['diferenca'] = d['primeiro']['winrate'] - d['segundo']['winrate'] if self.first[0] and self.second[0] else None
        return d

    def _cartas(self, base, min_n):
        rows = []
        for nm, copias in self.copias.items():
            c = self.por_carta[nm]
            jg = c['jogos'] or 1
            nao_usada_n = c['jogos'] - c['usada']
            nao_usada_w = c['jogos_w'] - c['usada_w']
            nao_vista_n = c['jogos'] - c['vista']
            nao_vista_w = c['jogos_w'] - c['vista_w']
            wr_u = c['usada_w'] / c['usada'] if c['usada'] else None
            wr_nu = nao_usada_w / nao_usada_n if nao_usada_n else None
            impacto = None
            if c['usada'] >= min_n and nao_usada_n >= min_n:
                impacto = _sh(c['usada_w'], c['usada'], base) - _sh(nao_usada_w, nao_usada_n, base)
            wr_v = c['vista_w'] / c['vista'] if c['vista'] else None
            wr_nv = nao_vista_w / nao_vista_n if nao_vista_n else None
            impacto_v = None
            if c['vista'] >= min_n and nao_vista_n >= min_n:
                impacto_v = _sh(c['vista_w'], c['vista'], base) - _sh(nao_vista_w, nao_vista_n, base)
            rows.append({
                'carta': nm, 'tipo': self.kind[nm], 'copias': copias,
                'jogadas_por_jogo': self.usos[nm] / jg,
                'vista_pct': c['vista'] / jg, 'usada_pct': c['usada'] / jg,
                'usada_dado_vista': (c['usada_dado_vista'] / c['vista']) if c['vista'] else None,
                'na_mao_no_fim': c['mao_fim'] / jg,
                'wr_usada': wr_u, 'wr_nao_usada': wr_nu, 'impacto_uso': impacto,
                'wr_vista': wr_v, 'wr_nao_vista': wr_nv, 'impacto_vista': impacto_v,
                'energia_basica': nm in self.basic_energy,
            })
        rows.sort(key=lambda r: -r['jogadas_por_jogo'])
        return rows

    def _fases(self, base, min_n):
        out = {}
        for nome, a, b in FASES:
            usos = self.fase_usos[nome]
            melhores = []
            for nm, (n, w) in self.fase_carta[nome].items():
                if n >= min_n:
                    melhores.append({'carta': nm, 'jogos': n, 'winrate': w / n,
                                     'delta': _sh(w, n, base) - base})
            melhores.sort(key=lambda r: -r['delta'])
            cb = self._lista_combos(self.combos[nome], base, min_n)
            out[nome] = {'vezes': f'{a}–{b}' if b < 10 ** 5 else f'{a}+',
                         'mais_usadas': [{'carta': c, 'jogadas': n, 'por_jogo': n / max(self.n, 1)}
                                         for c, n in usos.most_common(10)],
                         'melhores_cartas': melhores[:8], 'piores_cartas': melhores[::-1][:5],
                         'melhores_combos': cb[:8]}
        return out

    def _lista_combos(self, d, base, min_n):
        rows = []
        for (a, b), (n, w) in d.items():
            if n >= min_n:
                rows.append({'combo': [a, b], 'jogos': n, 'freq': n / max(self.n, 1), 'winrate': w / n,
                             'delta': _sh(w, n, base) - base})
        rows.sort(key=lambda r: -r['delta'])
        return rows

    def _combos(self, base, min_n):
        rows = self._lista_combos(self.combos['jogo'], base, min_n)
        return {'melhores': rows[:15], 'piores': rows[::-1][:8], 'minimo_jogos': min_n}

    def _hist(self, prem):
        out = []
        for k, cnt in enumerate(prem, 1):
            n = sum(cnt.values())
            vals = sorted(v for v, c in cnt.items() for _ in range(c))
            out.append({'premio': k, 'jogos_que_chegaram': n,
                        'hist': {str(v): cnt[v] for v in sorted(cnt)},
                        'media': statistics.fmean(vals) if vals else None,
                        'mediana': statistics.median(vals) if vals else None,
                        'p25': vals[len(vals) // 4] if vals else None,
                        'p75': vals[(3 * len(vals)) // 4] if vals else None})
        return out

    def _oponentes(self, meta):
        rows = []
        for nm, o in self.opp.items():
            n = o['n']
            p = o['w'] / n
            rows.append({'deck': nm, 'arquetipo': meta.get(nm, nm), 'jogos': n, 'winrate': p, 'ic95': _ic(p, n),
                         'wr_primeiro': o['f'][1] / o['f'][0] if o['f'][0] else None,
                         'wr_segundo': o['s'][1] / o['s'][0] if o['s'][0] else None,
                         'turnos': o['turns'] / n, 'premios_meus': o['pm'] / n, 'premios_dele': o['po'] / n})
        rows.sort(key=lambda r: r['winrate'])
        return rows

    def _arquetipos(self, meta):
        g = defaultdict(lambda: {'n': 0, 'w': 0.0, 'decks': set()})
        for nm, o in self.opp.items():
            a = g[meta.get(nm, nm)]
            a['n'] += o['n']
            a['w'] += o['w']
            a['decks'].add(nm)
        rows = [{'arquetipo': k, 'decks': len(v['decks']), 'jogos': v['n'], 'winrate': v['w'] / v['n'],
                 'ic95': _ic(v['w'] / v['n'], v['n'])} for k, v in g.items()]
        rows.sort(key=lambda r: r['winrate'])
        return rows


# =============================================================== teste completo
def testar_deck(deck_nome: str, partidas: int = 20, filtro: str | None = None, maximo: int | None = None,
                seed: int = 0, workers: int | None = None, progresso=None, pool: Pool | None = None,
                oponentes: list | None = None, agente: str = 'heuristic') -> dict:
    """Joga `partidas` partidas contra cada oponente e devolve as estatísticas (JSON-serializável).

    progresso(rotulo, feitos, total) é chamado a cada oponente concluído."""
    t0 = time.time()
    base = load_deck(deck_nome)
    if oponentes is None:
        oponentes, ignorados = listar_oponentes(deck_nome, filtro, maximo, seed)
    else:
        ignorados = []
    if not oponentes:
        raise ValueError('Nenhum oponente encontrado (confira o filtro).')
    meta = {o['name']: o['arquetipo'] for o in oponentes}
    agg = Agregador(base.cards)
    own = pool is None
    pool = pool or Pool(workers, agente)
    try:
        por_opp = pool.rodar(base.cards, oponentes, partidas, seed * 1_000_003, True, progresso=progresso,
                             rotulo='testando')
        for nm in sorted(por_opp):
            for r in por_opp[nm]:
                agg.add(nm, r)
    finally:
        if own:
            pool.__exit__()
    res = agg.resultado(meta, partidas)
    res.update({'deck': deck_nome, 'partidas_por_oponente': partidas, 'n_oponentes': len(oponentes),
                'ignorados': ignorados[:20], 'n_ignorados': len(ignorados), 'segundos': time.time() - t0,
                'lista': dict(Counter(base.cards)), 'filtro': filtro or '', 'seed': seed, 'agente': getattr(pool, 'agente', agente),
                'mulligans_por_jogo': agg.mull / max(agg.n, 1)})
    return res


# =============================================================== sugestões
def _escolher_gauntlet(oponentes, res_teste, n_dificeis, n_aleatorios, rng):
    por_nome = {o['name']: o for o in oponentes}
    dificeis, vistos = [], set()
    for r in res_teste['oponentes']:                           # já ordenado do pior para o melhor
        if r['arquetipo'] in vistos or r['deck'] not in por_nome:
            continue
        vistos.add(r['arquetipo'])
        dificeis.append(por_nome[r['deck']])
        if len(dificeis) >= n_dificeis:
            break
    resto = [o for o in oponentes if o not in dificeis]
    return dificeis + rng.sample(resto, min(n_aleatorios, len(resto)))


def _media(res_por_opp):
    ms = [statistics.fmean(r['res'] for r in rs) for rs in res_por_opp.values()]
    return statistics.fmean(ms)


def _se_diff(a, b, n):
    return math.sqrt(a * (1 - a) / n + b * (1 - b) / n)


def _candidatos(atual, pool, ranking_ruins, rng, n, travadas, somente=None):
    D = db()
    cont = Counter(atual)
    nome_de = {c: D.get(c).name for c in cont}
    por_nome = defaultdict(list)
    for c in cont:
        por_nome[nome_de[c]].append(c)
    tiraveis = []
    for nm in ranking_ruins:
        for c in por_nome.get(nm, []):
            if c not in travadas:
                tiraveis.append(c)
    outros = [c for c in cont if c not in tiraveis and c not in travadas]
    rng.shuffle(outros)
    tiraveis += outros[:3]
    if somente:             # o usuário deu a lista de cartas que podem entrar
        entram = list(somente)
    else:
        entram = [c for c in cont if cont[c] < 4 or D.get(c).basic_energy]
        extras = [c for c in pool if c not in cont]
        entram += rng.sample(extras, min(14, len(extras)))
    pares = [(o, i) for o in tiraveis for i in entram if o != i]
    rng.shuffle(pares)
    out, vistos = [], set()
    for o, i in pares:
        lst = list(atual)
        lst.remove(o)
        lst.append(i)
        key = tuple(sorted(lst))
        if key in vistos or validate(lst):
            continue
        vistos.add(key)
        out.append((lst, o, i))
        if len(out) >= n:
            break
    return out


def _ranking_ruins(res_teste, cartas_atuais=None):
    """Nomes de cartas do deck, das menos úteis para as mais úteis (pela estatística do teste)."""
    rows = [r for r in res_teste['cartas']]
    pontos = {}
    for r in rows:
        s = 0.0
        if r['impacto_uso'] is not None:
            s += r['impacto_uso']
        if r['usada_dado_vista'] is not None:
            s += 0.15 * (r['usada_dado_vista'] - 0.6)
        s -= 0.02 * r['na_mao_no_fim']
        if r['energia_basica']:
            s += 0.02           # energias: troca só se nada mais ruim
        pontos[r['carta']] = s
    return sorted(pontos, key=lambda k: pontos[k])


def sugerir_trocas(deck_nome: str, res_teste: dict, oponentes: list | None = None, rodadas: int = 3,
                   candidatos: int = 24, n_gauntlet=(8, 8), partidas_triagem: int = 16,
                   n_confirma: int = 60, partidas_confirma: int = 20, z: float = 1.0, seed: int = 7,
                   workers: int | None = None, progresso=None, pool: Pool | None = None,
                   travadas: list | None = None, agente: str = 'heuristic',
                   candidatas: list | None = None) -> dict:
    """Busca trocas (tira 1 cópia de uma carta, põe 1 de outra) que melhorem a taxa de vitória.

    Triagem: `candidatos` trocas por rodada contra um gauntlet (n_gauntlet[0] confrontos mais difíceis +
    n_gauntlet[1] aleatórios), mesmas sementes para todas. A melhor passa por confirmação em OUTROS oponentes
    com sementes novas; é aceita se a melhora for ≥ z erros-padrão."""
    t0 = time.time()
    D = db()
    base = load_deck(deck_nome)
    rng = random.Random(seed)
    if oponentes is None:
        oponentes, _ = listar_oponentes(deck_nome, res_teste.get('filtro') or None, None, res_teste.get('seed', 0))
    gauntlet = _escolher_gauntlet(oponentes, res_teste, n_gauntlet[0], n_gauntlet[1], rng)
    nomes_g = {o['name'] for o in gauntlet}
    resto = [o for o in oponentes if o['name'] not in nomes_g]
    independente = len(resto) >= 5
    conf = rng.sample(resto, min(n_confirma, len(resto))) if independente else list(gauntlet)
    pool_c = pool_de_cartas(base.cards)
    ruins = _ranking_ruins(res_teste)
    somente = ids_de_nomes(candidatas) if candidatas else None
    trav = {c for c in base.cards if D.get(c).name in (travadas or [])}
    own = pool is None
    pool = pool or Pool(workers, agente)
    atual = list(base.cards)
    trocas, testadas = [], []
    seed_tri = 5_000_000 + seed * 100_003
    try:
        def aval(lst, ops, n, sd, rot):
            return _media(pool.rodar(lst, ops, n, sd, False, progresso=progresso, rotulo=rot))

        ref_conf = aval(base.cards, conf, partidas_confirma, 9_000_000 + seed, 'referência')
        for rodada in range(1, rodadas + 1):
            s_atual = aval(atual, gauntlet, partidas_triagem, seed_tri, f'rodada {rodada}: deck atual')
            cands = _candidatos(atual, pool_c, ruins, rng, candidatos, trav, somente)
            res_c = pool.rodar_varios([c[0] for c in cands], gauntlet, partidas_triagem, seed_tri, False,
                                      progresso=progresso, rotulo=f'rodada {rodada}: {len(cands)} trocas')
            pontuados = [(_media(r), lst, o, inn) for r, (lst, o, inn) in zip(res_c, cands)]
            pontuados.sort(key=lambda x: -x[0])
            aceito = None
            for s, lst, o, inn in pontuados[:3]:
                if s <= s_atual:
                    break
                sd = 11_000_000 + rodada * 10_007 + seed
                a_old = aval(atual, conf, partidas_confirma, sd, f'rodada {rodada}: confirmando')
                a_new = aval(lst, conf, partidas_confirma, sd, f'rodada {rodada}: confirmando')
                n_tot = len(conf) * partidas_confirma
                se = _se_diff(a_new, a_old, n_tot)
                reg = {'tira': D.get(o).name, 'tira_id': o, 'poe': D.get(inn).name, 'poe_id': inn,
                       'triagem_antes': s_atual, 'triagem_depois': s,
                       'conf_antes': a_old, 'conf_depois': a_new, 'conf_jogos': n_tot,
                       'delta': a_new - a_old, 'ic95': 1.96 * se, 'rodada': rodada}
                if a_new - a_old >= z * se and a_new > a_old:
                    reg['aceita'] = True
                    aceito = (lst, reg)
                    testadas.append(reg)
                    break
                reg['aceita'] = False
                testadas.append(reg)
            if aceito is None:
                break
            atual = aceito[0]
            trocas.append(aceito[1])
        sd = 13_000_000 + seed
        final = aval(atual, conf, partidas_confirma * 2, sd, 'validação final')
        antes = aval(base.cards, conf, partidas_confirma * 2, sd, 'validação final')
    finally:
        if own:
            pool.__exit__()
    n_tot = len(conf) * partidas_confirma * 2
    return {'deck': deck_nome, 'trocas': trocas, 'testadas': testadas, 'lista': atual,
            'mudou': bool(trocas), 'antes': antes, 'depois': final, 'delta': final - antes,
            'ic95': 1.96 * _se_diff(final, antes, n_tot), 'jogos_validacao': n_tot,
            'referencia_confirmacao': ref_conf, 'confirmacao_independente': independente, 'n_gauntlet': len(gauntlet), 'n_confirmacao': len(conf),
            'gauntlet': [o['name'] for o in gauntlet], 'segundos': time.time() - t0,
            'resumo_lista': diff_listas(base.cards, atual)}


def ids_de_nomes(nomes) -> list:
    """Nomes de carta (inglês ou português) → ids. Levanta ValueError listando os desconhecidos."""
    D = db()
    ids, erros = [], []
    for nm in nomes:
        nm = nm.strip()
        if not nm:
            continue
        try:
            c = D.named(nm)
            ids.append(c[0].id if c else D.resolve(nm).id)
        except (KeyError, IndexError):
            erros.append(nm)
    if erros:
        raise ValueError('Cartas não encontradas: ' + ', '.join(erros))
    return ids


def diff_listas(antes, depois) -> dict:
    D = db()
    a, b = Counter(antes), Counter(depois)
    return {'entram': {D.get(k).name: n for k, n in (b - a).items()},
            'saem': {D.get(k).name: n for k, n in (a - b).items()}}


# =============================================================== salvar versões
def salvar_versao(deck_nome: str, cards: list, sugestao: dict | None = None, nome: str | None = None) -> dict:
    """Grava a nova lista em decks/meus/<base>_vN.txt (N = próxima versão livre) com meta de origem."""
    from . import deckbuilder as DB
    base_nome = DB.nome_seguro(deck_nome.split('/')[-1])
    raiz = base_nome.rsplit('_v', 1)[0] if base_nome.rsplit('_v', 1)[-1].isdigit() else base_nome
    if nome:
        alvo = DB.nome_seguro(nome)
    else:
        n = 2
        while (DECK_DIR / 'meus' / f'{raiz}_v{n}.txt').exists():
            n += 1
        alvo = f'{raiz}_v{n}'
    meta = {'origem': deck_nome}
    if sugestao:
        d = diff_listas(load_deck(deck_nome).cards, cards)
        meta['trocas'] = '; '.join([f'+{n} {k}' for k, n in d['entram'].items()] +
                                   [f'-{n} {k}' for k, n in d['saem'].items()])
        if 'antes' in sugestao:
            meta['winrate_validacao'] = f'{100 * sugestao["antes"]:.1f}% -> {100 * sugestao["depois"]:.1f}%'
    itens = [{'id': c, 'n': k} for c, k in Counter(cards).items()]
    r = DB.salvar(alvo, itens, False, meta)
    try:
        from .logbook import registrar
        registrar('decks', f'versão sugerida salva: {r["name"]} (origem {deck_nome})', trocas=meta.get('trocas'))
    except Exception:       # noqa: BLE001
        pass
    return r


# =============================================================== relatório em texto
def _pct(x, casas=0):
    return '—' if x is None else f'{100 * x:.{casas}f}%'


def relatorio_texto(r: dict, top: int = 10) -> str:
    L = []
    w = L.append
    w(f'══ Teste do deck {r["deck"]} ══')
    w(f'IA: {r.get("agente", "heuristic")} · {r["jogos"]} partidas contra {r["n_oponentes"]} decks ({r["partidas_por_oponente"]} cada) em '
      f'{r["segundos"]:.0f}s — vitórias: {_pct(r["winrate"], 1)} ±{100 * r["ic95"]:.1f}')
    o = r['ordem']
    w(f'\n▌ Ordem de jogo: começando {_pct(o["primeiro"]["winrate"], 1)} ({o["primeiro"]["jogos"]} partidas) · '
      f'em segundo {_pct(o["segundo"]["winrate"], 1)} ({o["segundo"]["jogos"]})'
      + (f' · diferença {100 * o["diferenca"]:+.1f} pp' if o['diferenca'] is not None else ''))
    cs = r['cartas']
    w('\n▌ Cartas mais jogadas (jogadas por partida · % das partidas em que apareceu · % em que foi usada)')
    for c in [x for x in cs if not x['energia_basica']][:top]:
        w(f'  {c["carta"]:<32} {c["jogadas_por_jogo"]:5.2f}/jogo   vista {_pct(c["vista_pct"]):>4}   '
          f'usada {_pct(c["usada_pct"]):>4}   ×{c["copias"]}')
    util = [x for x in cs if x['usada_dado_vista'] is not None and not x['energia_basica']]
    w('\n▌ Cartas que menos ajudaram (apareceu mas foi pouco usada / parada na mão no fim)')
    for c in sorted(util, key=lambda x: x['usada_dado_vista'])[:top // 2 + 1]:
        w(f'  {c["carta"]:<32} usada em {_pct(c["usada_dado_vista"]):>4} das partidas em que apareceu · '
          f'na mão ao fim: {c["na_mao_no_fim"]:.2f} cópias/jogo')
    com_imp = [x for x in cs if x['impacto_uso'] is not None]
    w('\n▌ Associadas a mais vitórias (vitória quando usada − quando não usada, encolhido)')
    for c in sorted(com_imp, key=lambda x: -x['impacto_uso'])[:5]:
        w(f'  {c["carta"]:<32} {100 * c["impacto_uso"]:+5.1f} pp   (usada {_pct(c["wr_usada"])} · não {_pct(c["wr_nao_usada"])})')
    w('▌ Associadas a menos vitórias')
    for c in sorted(com_imp, key=lambda x: x['impacto_uso'])[:5]:
        w(f'  {c["carta"]:<32} {100 * c["impacto_uso"]:+5.1f} pp   (usada {_pct(c["wr_usada"])} · não {_pct(c["wr_nao_usada"])})')
    w(f'\n▌ Combos (duas jogadas na MESMA vez; ≥{r["combos"]["minimo_jogos"]} partidas): vitória acima da média')
    for c in r['combos']['melhores'][:top]:
        w(f'  {c["combo"][0]} + {c["combo"][1]:<34} {100 * c["delta"]:+5.1f} pp   ({c["jogos"]} partidas, '
          f'vitória {_pct(c["winrate"])})')
    w('\n▌ Vez do jogador em que cada prêmio foi pego (média · mediana · quartis · partidas que chegaram lá)')
    for k in range(6):
        m, e = r['premios']['meu'][k], r['premios']['oponente'][k]
        if m['media'] is None:
            continue
        w(f'  {k + 1}º prêmio: vez {m["media"]:4.1f} (mediana {m["mediana"]:.0f}, {m["p25"]}–{m["p75"]}, '
          f'{m["jogos_que_chegaram"]} partidas)   | oponente: '
          + (f'vez {e["media"]:.1f}' if e['media'] is not None else '—'))
    w('  histograma do 1º prêmio (vez: partidas): ' + ', '.join(
        f'{v}:{n}' for v, n in r['premios']['meu'][0]['hist'].items()))
    w('\n▌ Por fase da partida (vezes de cada jogador)')
    for nome, f in r['fases'].items():
        w(f'  {nome.upper()} (vez {f["vezes"]})')
        w('    mais usadas: ' + ', '.join(f'{x["carta"]} ({x["por_jogo"]:.1f})' for x in f['mais_usadas'][:6]))
        w('    melhores cartas: ' + ', '.join(f'{x["carta"]} {100 * x["delta"]:+.1f}' for x in f['melhores_cartas'][:5]))
        w('    melhores combos: ' + '; '.join(f'{x["combo"][0]} + {x["combo"][1]} {100 * x["delta"]:+.1f}'
                                              for x in f['melhores_combos'][:3]))
    w('\n▌ Matchups mais difíceis (decks)')
    for x in r['oponentes'][:top]:
        w(f'  {_pct(x["winrate"]):>4} ±{100 * x["ic95"]:.0f}  {x["deck"]}  [{x["arquetipo"]}]')
    w('▌ Arquétipos mais difíceis')
    for x in [a for a in r['arquetipos'] if a['jogos'] >= 40][:top]:
        w(f'  {_pct(x["winrate"]):>4} ±{100 * x["ic95"]:.0f}  {x["arquetipo"]}  ({x["decks"]} decks, {x["jogos"]} partidas)')
    w('▌ Melhores confrontos')
    for x in r['oponentes'][::-1][:5]:
        w(f'  {_pct(x["winrate"]):>4}  {x["deck"]}  [{x["arquetipo"]}]')
    return '\n'.join(L)


def relatorio_sugestoes(s: dict) -> str:
    L = []
    w = L.append
    w(f'══ Sugestões de troca para {s["deck"]} ══')
    if not s['trocas']:
        w('Nenhuma troca testada melhorou o deck com confiança (a lista atual está num ótimo local para este conjunto '
          'de oponentes).')
    for i, t in enumerate(s['trocas'], 1):
        w(f'  {i}. −1 {t["tira"]}  →  +1 {t["poe"]}   '
          f'(confirmação: {_pct(t["conf_antes"], 1)} → {_pct(t["conf_depois"], 1)}, {100 * t["delta"]:+.1f} ±{100 * t["ic95"]:.1f} pp '
          f'em {t["conf_jogos"]} partidas)')
    rej = [t for t in s['testadas'] if not t['aceita']]
    if rej:
        w('  Promissoras na triagem mas não confirmadas: ' + '; '.join(
            f'−{t["tira"]} +{t["poe"]} ({100 * t["delta"]:+.1f} pp)' for t in rej[:4]))
    w(f'Validação final da nova lista: {_pct(s["antes"], 1)} → {_pct(s["depois"], 1)} '
      f'({100 * s["delta"]:+.1f} ±{100 * s["ic95"]:.1f} pp, {s["jogos_validacao"]} partidas, '
      f'{s["n_confirmacao"]} oponentes{" não usados na triagem" if s.get("confirmacao_independente") else " (poucos decks: os mesmos da triagem)"}) em {s["segundos"]:.0f}s')
    return '\n'.join(L)
