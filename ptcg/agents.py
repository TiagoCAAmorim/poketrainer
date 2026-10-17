"""Agentes de referência (aleatório e heurístico) e o laço de partida."""
from __future__ import annotations

import random
import re

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


def attach_value(g, p, energy_card, slot):
    need = line_needs(g, slot.name)
    if not need.get('total'):
        return 3
    t = energy_card.d.provides if energy_card.d.basic_energy else None
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
        t = d.provides
        needed = any(line_needs(g, s.name).get(t, 0) > 0 for s in pl.in_play()) if t else True
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


class HeuristicAgent(Agent):
    """Jogador por prioridades, genérico o bastante para qualquer carta do pool."""
    name = 'heuristic'

    def __init__(self, seed=None, epsilon=0.0):
        self.rng = random.Random(seed)
        self.epsilon = epsilon

    def act(self, g, pr):
        if self.epsilon and self.rng.random() < self.epsilon:
            return self.rng.randrange(len(pr.options))
        f = getattr(self, 'h_' + pr.hint, None)
        try:
            scores = f(g, pr) if f else self.generic(g, pr)
        except Exception:
            scores = self.generic(g, pr)
        return max(range(len(scores)), key=lambda i: (scores[i], self.rng.random()))

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
        return [o.value.d.hp / 10 - o.value.d.retreat * 6 - (25 if o.value.d.rule_box else 0) +
                (8 if o.value.d.abilities else 0) * 0 for o in pr.options]

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
        fake = type('E', (), {'d': type('D', (), {'provides': t, 'basic_energy': bool(t)})()})()
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
        pl, op = g.players[p], g.players[1 - p]
        k = o.kind
        if k == 'end':
            return 0
        if k == 'play_basic':
            return 62 if len(pl.bench) < 4 else 25
        if k == 'evolve':
            return 82
        if k == 'ability':
            s, ab = o.value
            if ab.impl is not None and ab.impl.self_ko:
                return 4
            return 72
        if k == 'stadium':
            return 38
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
            return 28 + attach_value(g, p, c, s) * 0.5
        if k == 'retreat':
            a, _ = best_attack(g, pl.active, op.active)
            if a is not None:
                return -1
            a2, dmg = best_attack(g, o.value, op.active)
            return 44 if a2 is not None and dmg > 0 else -1
        if k == 'attack':
            a = o.value
            me = pl.active
            dmg = g.estimate_attack(me, a, op.active)
            ko = op.active is not None and dmg >= g.hp_left(op.active)
            if dmg == 0 and a.text:
                return 7
            return 5 + min(dmg / 20, 15) + (5 if ko else 0)
        if k == 'trainer':
            return self.trainer_score(g, p, o.value)
        return 1

    def trainer_score(self, g, p, c):
        pl, op = g.players[p], g.players[1 - p]
        n, t, hand = c.name, _text(c), len(pl.hand)
        if 'your turn ends' in t:
            return 10
        if n == 'Rare Candy' or 'skipping the stage 1' in t:
            return 86
        if c.d.as_pokemon:
            return -1
        if re.search(r"switch in 1 of your opponent's benched", t):
            me = pl.active
            if op.active is not None and best_attack(g, me, op.active)[1] >= g.hp_left(op.active):
                return -1
            return 56 if any(best_attack(g, me, s)[1] >= g.hp_left(s) for s in op.bench) else -1
        if 'search your deck' in t and ('bench' in t):
            return 70 if g.bench_space(p) > 0 else -1
        if 'search your deck' in t:
            return 64 if c.d.is_supporter else 58
        if 'look at the top' in t:
            return 50
        if re.search(r'attach .*energy', t):
            return 66
        if 'heal' in t:
            return 42 if any(s.damage >= 60 for s in pl.in_play()) else -1
        if re.search(r'shuffle(?:s)? (?:their|your) hand', t) and 'each player' in t:
            return 46 if len(op.hand) >= 6 or hand <= 3 else 8
        if 'draw' in t:
            return 60 if hand <= 4 else (24 if hand <= 6 else 4)
        if 'switch your active' in t:
            a, _ = best_attack(g, pl.active, op.active)
            return 50 if a is None and any(best_attack(g, s, op.active)[0] for s in pl.bench) else -1
        if 'discard' in t and "opponent's" in t:
            return 40
        if c.d.is_stadium:
            return 36 if g.stadium is None or g.stadium.owner != p else -1
        if 'from your discard pile into your hand' in t:
            return 38
        return 20


AGENTS = {'random': RandomAgent, 'heuristic': HeuristicAgent}


def make_agent(spec: str, seed=None) -> Agent:
    """'random' | 'heuristic' | 'model:caminho/checkpoint.pt'"""
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
