"""Agentes de referência (aleatório e heurístico) e o laço de partida."""
from __future__ import annotations

import json
import os
import random
import re

from .core import NAME_TO_TYPE
from .engine import Game


class Agent:
    name = 'agent'

    def act(self, game: Game, prompt) -> int:
        raise NotImplementedError


class RandomAgent(Agent):
    name = 'random'

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def act(self, game, prompt):
        return self.rng.randrange(len(prompt.options))


# ======================================================================= heurística
_NEEDS: dict = {}


def line_needs(g, name):
    """Tipos de Energia pedidos pelos ataques deste Pokémon e das evoluções dele."""
    if name in _NEEDS:
        return _NEEDS[name]
    need = {'total': 0}
    stack, seen = [name], set()
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        for d in g.db.named(n):
            for a in d.attacks:
                for t in set(a.cost):
                    need[t] = max(need.get(t, 0), a.cost.count(t))
                need['total'] = max(need['total'], len(a.cost))
        stack += [x.name for x in g.db.cards.values() if x.evolves_from == n]
    _NEEDS[name] = need
    return need


def best_attack(g, slot, target=None):
    """(ataque, dano estimado) do melhor ataque usável agora; (None, 0) se nenhum."""
    best = (None, -1)
    p = slot.owner
    if g.players[p].active is not slot:
        for a in g.attacks_of(slot):
            if g.can_pay(slot, g.attack_cost(slot, a)):
                d = g.estimate_attack(slot, a, target)
                if d > best[1]:
                    best = (a, d)
        return best if best[0] else (None, 0)
    for a in g.attacks_of(slot):
        if g.can_use_attack(p, a):
            d = g.estimate_attack(slot, a, target)
            if d > best[1]:
                best = (a, d)
    return best if best[0] else (None, 0)


def energy_type(d):
    """Tipo que a Energia fornece: básicas pelo campo `provides`; especiais pelo texto ('provides Psychic Energy')."""
    if d.provides:
        return d.provides
    m = re.search(r'provides (\w+) Energy', d.text or '')
    return NAME_TO_TYPE.get(m.group(1)) if m else None


def attach_value(g, p, energy_card, slot):
    need = line_needs(g, slot.name)
    if not need.get('total'):
        return 3
    t = energy_type(energy_card.d)
    if t == 'C':
        t = None
    have = [u for _, us in g.energy_units(slot) for u in us]
    v = 10
    if t is not None and need.get(t, 0) > sum(1 for u in have if t in u):
        v = 50
    elif len(have) < need['total']:
        v = 35
    else:
        v = 6
    if slot is g.players[p].active:
        v += 6
    if slot.d.rule_box:
        v += 5
    if slot.d.abilities and slot.d.stage > 0 and all(a.damage <= 60 for a in slot.d.attacks):
        v -= 15     # Pokémon de suporte
    return v


def card_value(g, p, c):
    pl = g.players[p]
    d = c.d
    in_play = {s.name for s in pl.in_play()}
    if d.kind == 'pokemon':
        if d.stage > 0:
            if d.evolves_from in in_play:
                return 60
            mids = g.db.named(d.evolves_from) if d.evolves_from else []
            if d.stage == 2 and any(m.evolves_from in in_play for m in mids):
                return 50
            return 22
        v = 48 if d.name not in in_play else 30
        if g.bench_space(p) <= 0:
            v -= 25
        return v + (6 if d.rule_box else 0)
    if d.kind == 'energy':
        t = energy_type(d)
        needed = any(line_needs(g, s.name).get(t, 0) > 0 for s in pl.in_play()) if t and t != 'C' else True
        return 40 if needed else 14
    if d.name == 'Rare Candy':
        return 46 if any(h.d.stage == 2 for h in pl.hand) else 20
    if d.is_supporter:
        return 34
    if d.is_tool:
        return 20
    if d.is_stadium:
        return 16
    return 28


def _text(c):
    return (c.d.text or '').lower()


# Pesos da heurística. `melhorar_heuristica.py` otimiza estes valores contra o jogador aleatório e grava os
# melhores em ptcg/data/heuristica.json (carregado aqui por cima dos padrões).
DEFAULT_PARAMS = {
    'deck_low': 9,          # com tantas cartas (ou menos) no baralho, para de comprar cartas (evita perder por falta)
    'stall_turn': 14, 'stall_margin': 0,   # após este turno só compra extra se o baralho for maior que o do oponente
    'deck_search_low': 3,   # idem para buscas no baralho
    'play_basic': 62, 'play_basic_full': 25,
    'evolve': 82, 'ability': 72, 'stadium': 38,
    'attach_base': 28, 'attach_w': 0.5,
    'retreat': 44, 'retreat_dmg': 10, 'retreat_better': 40, 'retreat_gain': 40,
    'zero_dmg_value': 40, 'ko_value': 60,
    'attack_base': 5, 'attack_dmg_div': 20, 'attack_dmg_cap': 15, 'attack_ko': 5, 'attack_zero_text': 7,
    'rare_candy': 86, 'search_bench': 70, 'search_supporter': 64, 'search_item': 58,
    'draw_low_hand': 60, 'draw_mid_hand': 24, 'draw_high_hand': 4,
    'gust': 56, 'switch': 50, 'heal': 42, 'trainer_default': 20,
    'setup_hp_w': 1.0, 'setup_retreat_w': 6, 'setup_rule_box': 25,
}
PARAMS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'heuristica.json')


def load_params(path=PARAMS_FILE):
    """Pesos padrão + os ajustados salvos em ptcg/data/heuristica.json (se existir)."""
    out = dict(DEFAULT_PARAMS)
    try:
        with open(path, encoding='utf-8') as f:
            out.update({k: v for k, v in json.load(f).items() if k in DEFAULT_PARAMS})
    except (OSError, ValueError):
        pass
    return out


_DRAW_RE = re.compile(r'\bdraw\b|\bdraws\b')


class HeuristicAgent(Agent):
    """Jogador por prioridades, genérico o bastante para qualquer carta do pool."""
    name = 'heuristic'
    _params_cache = None

    def __init__(self, seed=None, epsilon=0.0, params=None):
        self.rng = random.Random(seed)
        self.epsilon = epsilon
        if params is None:
            if HeuristicAgent._params_cache is None:
                HeuristicAgent._params_cache = load_params()
            params = HeuristicAgent._params_cache
        self.P = params

    def act(self, g, pr):
        if self.epsilon and self.rng.random() < self.epsilon:
            return self.rng.randrange(len(pr.options))
        f = getattr(self, 'h_' + pr.hint, None)
        try:
            scores = f(g, pr) if f else self.generic(g, pr)
        except Exception:
            scores = self.generic(g, pr)
        order = sorted(range(len(scores)), key=lambda i: (scores[i], self.rng.random()), reverse=True)
        if pr.hint == 'main' and not g.players[pr.player].bench:
            for i in order:            # só um Pokémon em jogo: não escolhe ação que faz o jogo acabar contra nós
                if pr.options[i].kind in ('ability', 'trainer', 'tool', 'stadium') and self._suicide(g, pr, i):
                    continue
                return i
        return order[0]

    def _no_draw(self, g, p):
        """True se comprar além do normal arrisca perder por falta de cartas (ou a corrida de baralho)."""
        P = self.P
        mine, theirs = len(g.players[p].deck), len(g.players[1 - p].deck)
        return mine <= P['deck_low'] or (g.turn >= P['stall_turn'] and mine <= theirs + P['stall_margin'])

    def attack_value(self, g, slot, opp):
        """Valor do melhor ataque do Pokémon agora (None se não pode atacar). Ataques sem dano de texto
        (contadores etc.) valem `zero_dmg_value`; nocautear o ativo adversário soma `ko_value`."""
        a, d = best_attack(g, slot, opp)
        if a is None:
            return None
        if d == 0 and a.text:
            d = self.P['zero_dmg_value']
        return d + (self.P['ko_value'] if opp is not None and d >= g.hp_left(opp) else 0)

    @staticmethod
    def _suicide(g, pr, i):
        """True se executar a opção `i` encerra a partida com derrota imediata do jogador (verifica num clone)."""
        try:
            c = g.clone()
            c.step(i)
            return c.done and c.winner != pr.player
        except Exception:
            return False

    def evaluate(self, g, pr=None):
        """Sugestão para a interface: 100% na opção escolhida pela heurística, sem avaliação de posição."""
        pr = pr or g.prompt
        best = self.act(g, pr)
        return [1.0 if i == best else 0.0 for i in range(len(pr.options))], None

    # ------------------------------------------------------------ escolhas genéricas
    def generic(self, g, pr):
        p = pr.player
        out = []
        for o in pr.options:
            if o.kind == 'done':
                out.append(-5 if pr.hint in ('discard', 'retreat_energy', 'discard_energy') else 0)
            elif o.kind == 'yes':
                out.append(1)
            elif o.kind == 'no':
                out.append(0)
            elif o.kind == 'card':
                v = card_value(g, p, o.value)
                out.append(-v if pr.hint in ('discard', 'bottom', 'discard_energy') else v)
            elif o.kind in ('slot', 'opp_slot'):
                out.append(self._slot_score(g, p, o.value, pr.hint))
            else:
                out.append(self.rng.random())
        return out

    def _slot_score(self, g, p, s, hint):
        if s.owner != p:
            return s.d.base_prizes * 20 - g.hp_left(s) / 10
        if hint in ('heal_target',):
            return s.damage
        if hint == 'move_from':
            return s.damage
        return g.hp_left(s) / 10

    def h_first(self, g, pr):
        return [1 if o.value else 0 for o in pr.options]

    def h_setup_active(self, g, pr):
        P = self.P
        return [o.value.d.hp / 10 * P['setup_hp_w'] - o.value.d.retreat * P['setup_retreat_w'] -
                (P['setup_rule_box'] if o.value.d.rule_box else 0) for o in pr.options]

    def h_setup_bench(self, g, pr):
        return [0 if o.kind == 'done' else 10 for o in pr.options]

    def h_promote(self, g, pr):
        p = pr.player
        opp = g.players[1 - p].active
        out = []
        for o in pr.options:
            s = o.value
            _, dmg = best_attack(g, s, opp)
            ko = opp is not None and dmg >= g.hp_left(opp)
            if dmg == 0 and best_attack(g, s, opp)[0] is not None:
                dmg = self.P['zero_dmg_value']
            out.append(dmg / 10 + (50 if ko else 0) + g.hp_left(s) / 30 - s.d.retreat * 2)
        return out

    h_switch = h_promote

    def h_gust(self, g, pr):
        me = g.players[pr.player].active
        out = []
        for o in pr.options:
            s = o.value
            _, dmg = best_attack(g, me, s) if me else (None, 0)
            ko = dmg >= g.hp_left(s)
            out.append((100 + 30 * s.d.base_prizes if ko else 0) - g.hp_left(s) / 10 + s.d.base_prizes * 5)
        return out

    def h_counters(self, g, pr):
        return [100 - g.hp_left(o.value) / 10 + (10 * o.value.d.base_prizes if g.hp_left(o.value) <= 60 else 0)
                if o.value is not None else -1 for o in pr.options]

    h_damage_target = h_counters
    h_bench_target = h_counters

    def h_attach_target(self, g, pr):
        t = pr.data.get('energy')
        fake = type('E', (), {'d': type('D', (), {'provides': t, 'basic_energy': bool(t), 'text': ''})()})()
        return [attach_value(g, pr.player, fake, o.value) if o.value is not None else -1 for o in pr.options]

    def h_discard_energy_any(self, g, pr):
        """'Descarte qualquer quantidade de Energia' (Bellowing Thunder etc.): descarta só o necessário."""
        p = pr.player
        opp = g.players[1 - p].active
        need = g.hp_left(opp) if opp else 0
        chosen = pr.data.get('chosen', 0)
        per = 70
        m = re.search(r'(\d+)', (getattr(pr.source, 'd', None) and ''.join(a.text for a in pr.source.d.attacks)) or '')
        if m:
            per = int(m.group(1))
        out = []
        for o in pr.options:
            if o.kind == 'done':
                out.append(50 if chosen > 0 and chosen * per >= need else -50)
            else:
                out.append(10)
        return out

    def h_mode(self, g, pr):
        return [self.rng.random() for _ in pr.options]

    # ------------------------------------------------------------ fase principal
    def h_main(self, g, pr):
        return [self.score_main(g, pr.player, o) for o in pr.options]

    def score_main(self, g, p, o):
        P = self.P
        pl, op = g.players[p], g.players[1 - p]
        k = o.kind
        if k == 'end':
            return 0
        if k == 'play_basic':
            return P['play_basic'] if len(pl.bench) < 4 else P['play_basic_full']
        if k == 'evolve':
            return P['evolve']
        if k == 'ability':
            s, ab = o.value
            if ab.impl is not None and ab.impl.self_ko:
                return 4
            if self._no_draw(g, p) and _DRAW_RE.search((ab.text or '').lower()):
                return -2       # não esvazia o próprio baralho
            return P['ability']
        if k == 'stadium':
            t = _text(o.value) if o.value is not None else ''
            if _DRAW_RE.search(t):
                if self._no_draw(g, p):
                    return -2
                if 'discard' in t:      # Prism Tower & cia.: gastar cartas para comprar só com a mão cheia
                    return 8 if len(pl.hand) >= 8 else -1
            return P['stadium']
        if k == 'discard_fossil':
            return -1
        if k == 'tool':
            c, s = o.value
            t = _text(c)
            if 'hp' in t:
                return 30 if s is pl.active or s.d.rule_box else 18
            if 'more damage' in t:
                return 30 if s is pl.active and s.d.attacks else 8
            if 'retreat cost' in t:
                return 24 if s is pl.active else 6
            return 14
        if k == 'attach':
            c, s = o.value
            return P['attach_base'] + attach_value(g, p, c, s) * P['attach_w']
        if k == 'retreat':
            va = self.attack_value(g, pl.active, op.active)
            vb = self.attack_value(g, o.value, op.active)
            if vb is None:
                return -1
            if va is None:
                return P['retreat'] + (P['retreat_dmg'] if vb > 0 else 0)
            return P['retreat_better'] if vb >= va + P['retreat_gain'] else -1
        if k == 'attack':
            a = o.value
            me = pl.active
            dmg = g.estimate_attack(me, a, op.active)
            ko = op.active is not None and dmg >= g.hp_left(op.active)
            if dmg == 0 and a.text:
                return P['attack_zero_text']
            return P['attack_base'] + min(dmg / P['attack_dmg_div'], P['attack_dmg_cap']) + (P['attack_ko'] if ko else 0)
        if k == 'trainer':
            return self.trainer_score(g, p, o.value)
        return 1

    def trainer_score(self, g, p, c):
        P = self.P
        pl, op = g.players[p], g.players[1 - p]
        n, t, hand = c.name, _text(c), len(pl.hand)
        ndeck = len(pl.deck)
        if 'your turn ends' in t:
            return 10
        if self._no_draw(g, p) and _DRAW_RE.search(t):
            return -2           # não esvazia o próprio baralho
        if ndeck <= P['deck_search_low'] and 'search your deck' in t:
            return -2
        if n == 'Rare Candy' or 'skipping the stage 1' in t:
            return P['rare_candy']
        if c.d.as_pokemon:
            return -1
        if re.search(r"switch in 1 of your opponent's benched", t):
            me = pl.active
            if op.active is not None and best_attack(g, me, op.active)[1] >= g.hp_left(op.active):
                return -1
            return P['gust'] if any(best_attack(g, me, s)[1] >= g.hp_left(s) for s in op.bench) else -1
        if 'search your deck' in t and ('bench' in t):
            return P['search_bench'] if g.bench_space(p) > 0 else -1
        if 'search your deck' in t:
            return P['search_supporter'] if c.d.is_supporter else P['search_item']
        if 'look at the top' in t:
            return 50
        if re.search(r'attach .*energy', t):
            return 66
        if 'heal' in t:
            return P['heal'] if any(s.damage >= 60 for s in pl.in_play()) else -1
        if re.search(r'shuffle(?:s)? (?:their|your) hand', t) and 'each player' in t:
            return 46 if len(op.hand) >= 6 or hand <= 3 else 8
        if 'draw' in t:
            return P['draw_low_hand'] if hand <= 4 else (P['draw_mid_hand'] if hand <= 6 else P['draw_high_hand'])
        if 'switch your active' in t:
            a, _ = best_attack(g, pl.active, op.active)
            return P['switch'] if a is None and any(best_attack(g, s, op.active)[0] for s in pl.bench) else -1
        if 'discard' in t and "opponent's" in t:
            return 40
        if c.d.is_stadium:
            return 36 if g.stadium is None or g.stadium.owner != p else -1
        if 'from your discard pile into your hand' in t:
            return 38
        return P['trainer_default']


AGENTS = {'random': RandomAgent, 'heuristic': HeuristicAgent}


def make_agent(spec: str, seed=None) -> Agent:
    """'random' | 'heuristic' | 'heuristic:{json com pesos}' | 'model:caminho/checkpoint.pt'"""
    if spec.startswith('heuristic:'):
        params = dict(DEFAULT_PARAMS)
        params.update(json.loads(spec.split(':', 1)[1]))
        return HeuristicAgent(seed=seed, params=params)
    if spec.startswith('model:'):
        from .ai.agent import TorchAgent
        return TorchAgent(spec.split(':', 1)[1])
    return AGENTS[spec](seed=seed)


def play_game(deck0, deck1, agents, seed=None, max_decisions=20000, names=('Jogador 1', 'Jogador 2')) -> Game:
    g = Game(deck0, deck1, seed=seed, names=names)
    while not g.done:
        if g.decisions > max_decisions:
            raise RuntimeError('Partida excedeu o limite de decisões')
        pr = g.prompt
        g.step(agents[pr.player].act(g, pr))
    return g
