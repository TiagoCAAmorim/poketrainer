"""Motor de regras do Pokémon TCG (formato Standard atual, regras como no Pokémon TCG Live).

A partida inteira é um *generator*: toda decisão é um `yield Prompt(...)` com as opções legais.
Efeitos de cartas usam os auxiliares desta classe (`yield from g.choose_cards(...)`).

Efeitos contínuos (Habilidades passivas, Ferramentas, Estádios, Energias especiais e efeitos
temporários) são consultados por GANCHOS:
    g.fold('hp', 120, slot=s)            → valor modificado por todos os ganchos 'hp'
    g.allowed('can_retreat', slot=s)     → falso se algum gancho negar
    g.anyhook('prevent_attack_effects', ...) → verdadeiro se algum gancho prevenir
    yield from g.emit('knocked_out', ...) → dispara gatilhos

Ganchos de consulta: hp, retreat_cost, attack_cost, energy_units, types, weakness, damage_out, damage_out_bench,
damage_in, survive, prevent_attack_effects, prevent_counters, prevent_trainer_effects,
condition_immune, can_heal, can_attack, can_retreat, can_play, ability_blocked, tools_blocked,
bench_max, tool_slots, prizes, can_evolve_early, evolves_from, extra_attacks, checkup_counters,
first_turn_attack, damage_counters_movable.
Eventos: turn_end, bench_played, evolved, energy_attached, damaged_by_attack, knocked_out,
moved_to_bench, moved_to_active, trainer_played, checkup.
"""
from __future__ import annotations

import random
from typing import Optional

from .core import (ANY, COLORLESS, DEFAULT_BENCH, EXCLUSIVE_CONDITIONS, AttackCtx, Card, GameOver, Option,
                   Player, PokemonSlot, Prompt, Src, TempEffect)


def run(res):
    """Permite que efeitos sejam funções normais ou generators."""
    if res is not None and hasattr(res, 'send'):
        return (yield from res)
    return res


class Game:
    MAX_TURNS = 150

    def __init__(self, deck0, deck1, seed: Optional[int] = None, names=('Jogador 1', 'Jogador 2'),
                 first_player: Optional[int] = None):
        """deck0/deck1: listas de CardDef, ids ('TWM-130') ou nomes."""
        from .carddb import db
        self.db = db()
        self.seed = seed if seed is not None else random.randrange(2 ** 31)
        self.rng = random.Random(self.seed)
        self.deck_lists = [[self._as_def(x).id for x in deck0], [self._as_def(x).id for x in deck1]]
        self.names = tuple(names)
        self.forced_first = first_player
        uid = 0
        self.players: list[Player] = []
        for i, dl in enumerate(self.deck_lists):
            cards = []
            for cid in dl:
                cards.append(Card(uid, self.db.get(cid), i))
                uid += 1
            self.players.append(Player(i, cards, names[i]))
        self.turn = 0
        self.current = 0
        self.first_player = 0
        self.stadium: Optional[Card] = None
        self.effects: list[TempEffect] = []
        self.ko_log: list[dict] = []
        self.prize_log: list[tuple] = []   # (turno, quem pegou, quantas)
        self.log: list[dict] = []
        self.history: list[int] = []
        self.winner: Optional[int] = None
        self.end_reason = ''
        self.done = False
        self.setup_done = False
        self.prompt: Optional[Prompt] = None
        self.decisions = 0
        self.turn_ended = False          # "Your turn ends." de efeitos
        self.manual_main = getattr(self, 'manual_main', False)   # não auto-resolver a fase principal
        self._actx: Optional[AttackCtx] = None
        self._gen = self._flow()
        self._advance(None)

    def _as_def(self, x):
        if hasattr(x, 'id') and hasattr(x, 'kind'):
            return x
        if x in self.db.cards:
            return self.db.cards[x]
        return self.db.resolve(x)

    # ------------------------------------------------------------------ API
    def step(self, index: int):
        if self.done:
            raise RuntimeError('Jogo terminado')
        opt = self.prompt.options[index]
        self.history.append(index)
        self.decisions += 1
        self._advance(opt)

    def refresh(self):
        """Recalcula as opções da fase principal (usado por testes/editor de posição)."""
        if self.prompt is not None and self.prompt.hint == 'main':
            self._advance(Option('', None, 'noop'))

    def clone(self) -> 'Game':
        g = Game(self.deck_lists[0], self.deck_lists[1], seed=self.seed, names=self.names,
                 first_player=self.forced_first)
        for i in self.history:
            g.step(i)
        return g

    def _advance(self, value):
        while True:
            try:
                req = self._gen.send(value)
            except StopIteration:
                self.done = True
                self.prompt = None
                return
            value = None
            if not req.options:
                raise RuntimeError(f'Prompt sem opções: {req.text}')
            if len(req.options) == 1 and not (self.manual_main and req.hint == 'main'):
                value = req.options[0]
                continue
            self.prompt = req
            return

    # ------------------------------------------------------------- utilidades
    def say(self, msg, kind='info'):
        self.log.append({'turn': self.turn, 'msg': msg, 'kind': kind})

    def flip(self, who=None) -> bool:
        heads = self.rng.random() < 0.5
        self.say(f'Moeda: {"cara" if heads else "coroa"}', 'coin')
        return heads

    def flips(self, n) -> int:
        return sum(self.flip() for _ in range(n))

    def flip_until_tails(self) -> int:
        n = 0
        while self.flip():
            n += 1
        return n

    def opp(self, p):
        return 1 - p

    def is_active(self, slot) -> bool:
        return self.players[slot.owner].active is slot

    def in_play(self, slot) -> bool:
        return slot in self.players[slot.owner].in_play()

    def slot_pos(self, slot) -> int:
        pl = self.players[slot.owner]
        if pl.active is slot:
            return 0
        return 1 + pl.bench.index(slot) if slot in pl.bench else -1

    def slot_label(self, slot) -> str:
        pos = self.slot_pos(slot)
        return f'{slot.name} ({"Ativo" if pos == 0 else f"Banco {pos}" if pos > 0 else "fora de jogo"})'

    def shuffle(self, p):
        self.rng.shuffle(self.players[p].deck)

    def draw(self, p, n=1) -> int:
        pl = self.players[p]
        k = 0
        for _ in range(max(0, n)):
            if not pl.deck:
                break
            pl.hand.append(pl.deck.pop(0))
            k += 1
        return k

    def draw_until(self, p, n) -> int:
        return self.draw(p, n - len(self.players[p].hand))

    def discard_cards(self, cards):
        for c in cards:
            self.players[c.owner].discard.append(c)

    def discard_hand(self, p):
        pl = self.players[p]
        pl.discard.extend(pl.hand)
        pl.hand = []

    def hand_to_deck(self, p, bottom=False):
        pl = self.players[p]
        hand, pl.hand = pl.hand, []
        self.rng.shuffle(hand)
        pl.deck.extend(hand)
        if not bottom:
            self.shuffle(p)
        return len(hand)

    def prizes_taken(self, p) -> int:
        return 6 - len(self.players[p].prizes)

    def kod_last_turn(self, p, pred=None) -> bool:
        """Algum Pokémon de p foi nocauteado durante o último turno do oponente?"""
        return any(e['owner'] == p and e['turn'] == self.turn - 1 and (pred is None or pred(e))
                   for e in self.ko_log)

    def first_turn(self, p) -> bool:
        return self.players[p].turns_taken <= 1

    # --------------------------------------------------------------- ganchos
    def _sources(self):
        out = []
        st = self.stadium
        if st is not None and st.d.impl is not None:
            out.append((Src('stadium', st.owner, st), st.d.impl.hooks, st.d.impl.events))
        for te in self.effects:
            out.append((Src('temp', te.owner, None, te.target, te), te.hooks, te.events))
        tools_on = not self._tools_blocked(out)
        for p in (0, 1):
            for s in self.players[p].in_play():
                for ab in s.d.abilities:
                    im = ab.impl
                    if im is not None and (im.hooks or im.events) and self.ability_active(s, ab, out):
                        out.append((Src('ability', p, s.top, s, ab), im.hooks, im.events))
                if tools_on:
                    for t in s.tools:
                        if t.d.impl is not None:
                            out.append((Src('tool', p, t, s), t.d.impl.hooks, t.d.impl.events))
                for e in s.energy:
                    if e.d.impl is not None and (e.d.impl.hooks or e.d.impl.events):
                        out.append((Src('energy', p, e, s), e.d.impl.hooks, e.d.impl.events))
        return out

    def _tools_blocked(self, base):
        for src, hooks, _ in base:
            f = hooks.get('tools_blocked')
            if f and f(self, src):
                return True
        return False

    def ability_active(self, slot, ab, base=None) -> bool:
        """A Habilidade `ab` deste Pokémon está funcionando (não bloqueada)?"""
        if base is None:
            base = []
            st = self.stadium
            if st is not None and st.d.impl is not None:
                base.append((Src('stadium', st.owner, st), st.d.impl.hooks, None))
            for te in self.effects:
                base.append((Src('temp', te.owner, None, te.target, te), te.hooks, None))
        for src, hooks, _ in base:
            f = hooks.get('ability_blocked')
            if f and f(self, src, slot=slot, ability=ab):
                return False
        for p in (0, 1):   # bloqueadores que são Habilidades (sem recursão)
            for s in self.players[p].in_play():
                if s is slot:
                    continue
                for a2 in s.d.abilities:
                    im = a2.impl
                    if im is not None and 'ability_blocked' in im.hooks:
                        if im.hooks['ability_blocked'](self, Src('ability', p, s.top, s, a2), slot=slot, ability=ab):
                            return False
        return True

    def hooks(self, name):
        for src, hooks, _ in self._sources():
            f = hooks.get(name)
            if f is not None:
                yield src, f

    def fold(self, name, value, **ctx):
        skip_target = ctx.pop('_skip_target', None)
        for src, f in self.hooks(name):
            if skip_target is not None and src.kind != 'stadium' and (
                    src.slot is skip_target or (src.kind == 'ability' and src.owner == skip_target.owner)):
                continue      # "ignora efeitos no Pokémon Defensor": inclui Habilidades de outros Pokémon do dono (ruling 2424)
            r = f(self, src, value, **ctx)
            if r is not None:
                value = r
        return value

    def allowed(self, name, **ctx) -> bool:
        for src, f in self.hooks(name):
            if f(self, src, **ctx) is False:
                return False
        return True

    def anyhook(self, name, **ctx) -> bool:
        for src, f in self.hooks(name):
            if f(self, src, **ctx):
                return True
        return False

    def emit(self, event, **ctx):
        handlers = [(src, ev[event]) for src, _, ev in self._sources() if ev and event in ev]
        for src, f in handlers:
            yield from run(f(self, src, **ctx))

    def add_effect(self, name, owner, hooks=None, events=None, target=None, duration='opp_next_turn',
                   while_active=False, **data):
        """duration: 'this_turn' | 'opp_next_turn' | 'my_next_turn' | int (turno de expiração)."""
        exp = {'this_turn': self.turn, 'opp_next_turn': self.turn + 1, 'my_next_turn': self.turn + 2}.get(
            duration, duration)
        te = TempEffect(name, owner, hooks or {}, events or {}, target, exp, while_active, data)
        self.effects.append(te)
        return te

    def _slot_left(self, slot, evolved=False):
        """Remove efeitos 'enquanto estiver no Ativo' quando o Pokémon sai do Ativo ou evolui."""
        self.effects = [e for e in self.effects if not (e.target is slot and e.while_active)]

    # --------------------------------------------------------- estatísticas
    def hp(self, slot) -> int:
        return max(0, self.fold('hp', slot.d.hp, slot=slot))

    def hp_left(self, slot) -> int:
        return self.hp(slot) - slot.damage

    def full_hp(self, slot) -> bool:
        return slot.damage <= 0

    def types(self, slot) -> list:
        return self.fold('types', list(slot.d.types), slot=slot)

    def has_type(self, slot, t) -> bool:
        return t in self.types(slot)

    def weakness(self, slot):
        return self.fold('weakness', (slot.d.weakness, 2), slot=slot)

    def retreat_cost(self, slot) -> int:
        return max(0, self.fold('retreat_cost', slot.d.retreat, slot=slot))

    def energy_units(self, slot):
        """[(carta, [unidades])] — unidade = frozenset de tipos que ela pode pagar."""
        out = []
        for e in slot.energy:
            d = e.d
            if d.basic_energy:
                units = [frozenset({d.provides})]
            elif d.impl is not None and d.impl.units is not None:
                units = d.impl.units(self, e, slot)
            else:
                units = [COLORLESS]
            units = self.fold('energy_units', units, slot=slot, card=e)
            out.append((e, units))
        return out

    def energy_count(self, slot, t=None) -> int:
        n = 0
        for _, units in self.energy_units(slot):
            for u in units:
                if t is None or t in u:
                    n += 1
        return n

    def has_energy_type(self, slot, t) -> bool:
        return self.energy_count(slot, t) > 0

    def attack_cost(self, slot, atk) -> list:
        cost = self.fold('attack_cost', list(atk.cost), slot=slot, attack=atk)
        im = atk.impl
        if im is not None and im.cost_mod is not None:
            cost = im.cost_mod(self, slot, cost)
        return cost

    def can_pay(self, slot, cost, units=None) -> bool:
        if units is None:
            units = [u for _, us in self.energy_units(slot) for u in us]
        specific = sorted([t for t in cost if t != 'C'], key=lambda t: sum(1 for u in units if t in u))
        colorless = len(cost) - len(specific)
        used = [False] * len(units)

        def bt(i):
            if i == len(specific):
                return sum(1 for x in used if not x) >= colorless
            t = specific[i]
            for j, u in enumerate(units):
                if not used[j] and t in u:
                    used[j] = True
                    if bt(i + 1):
                        return True
                    used[j] = False
            return False
        return bt(0)

    @staticmethod
    def playable_basic(c) -> bool:
        """Básico que pode ser jogado da mão (alguns só entram por efeito, ex.: Palafin ex)."""
        return c.d.is_basic and not any(ab.impl is not None and ab.impl.hand_blocked for ab in c.d.abilities)

    @staticmethod
    def setup_active_ok(c) -> bool:
        """Pode ser colocado como Ativo na preparação mesmo sem ser Básico (ex.: Cinderace)."""
        return c.d.kind == 'pokemon' and any(ab.impl is not None and ab.impl.kind == 'setup' for ab in c.d.abilities)

    def bench_max(self, p) -> int:
        return self.fold('bench_max', DEFAULT_BENCH, player=p)

    def bench_space(self, p) -> int:
        return max(0, self.bench_max(p) - len(self.players[p].bench))

    def tool_slots(self, slot) -> int:
        return self.fold('tool_slots', 1, slot=slot)

    def attacks_of(self, slot) -> list:
        return list(slot.d.attacks) + self.fold('extra_attacks', [], slot=slot)

    def has_ability(self, slot) -> bool:
        return any(self.ability_active(slot, a) for a in slot.d.abilities)

    # --------------------------------------------------------- escolhas
    def ask(self, p, hint, text, options, source=None, **data):
        opt = yield Prompt(p, hint, text, options, source, data)
        return opt

    def yes_no(self, p, text, hint='yes_no', source=None):
        opt = yield Prompt(p, hint, text, [Option('Sim', True, 'yes'), Option('Não', False, 'no')], source)
        return opt.value

    def choose_option(self, p, text, labels, hint='mode', source=None):
        """Escolhe entre modos textuais; retorna o índice."""
        opt = yield Prompt(p, hint, text, [Option(l, i, 'text') for i, l in enumerate(labels)], source)
        return opt.value

    def choose_cards(self, p, cards, max_n, min_n=0, hint='pick', text='Escolha', source=None,
                     key=None, labeler=None, **data):
        key = key or (lambda c: c.d.id)
        chosen, pool = [], list(cards)
        deck_uids = {c.uid for c in self.players[p].deck}
        if pool and all(c.uid in deck_uids for c in pool):
            data = dict(data, deck_view=True)     # busca no próprio baralho: a interface pode mostrá-lo inteiro
        while len(chosen) < max_n and pool:
            opts, seen = [], set()
            for c in pool:
                k = key(c)
                if k in seen:
                    continue
                seen.add(k)
                opts.append(Option(labeler(c) if labeler else c.name, c, 'card', card=c))
            if len(chosen) >= min_n:
                opts.append(Option('Concluir', None, 'done'))
            opt = yield Prompt(p, hint, f'{text} ({len(chosen)}/{max_n})', opts, source,
                               dict(data, chosen=len(chosen), max=max_n, picked=list(chosen)))
            if opt.value is None:
                break
            chosen.append(opt.value)
            pool.remove(opt.value)
        return chosen

    def choose_slot(self, p, slots, hint, text, source=None, optional=False, **data):
        slots = list(slots)
        if not slots:
            return None
        opts = []
        for s in slots:
            o = s.owner
            opts.append(Option(self.slot_label(s), s, 'slot' if o == p else 'opp_slot', card=s.top,
                               target=(o, self.slot_pos(s))))
        if optional:
            opts.append(Option('Nenhum', None, 'done'))
        opt = yield Prompt(p, hint, text, opts, source, data)
        return opt.value

    def search_deck(self, p, pred, max_n, hint='search', text='Buscar no baralho', source=None, min_n=0,
                    shuffle=True, reveal=True):
        pl = self.players[p]
        cands = [c for c in pl.deck if pred(c)]
        chosen = yield from self.choose_cards(p, cands, max_n, min_n, hint, text, source)
        for c in chosen:
            pl.deck.remove(c)
        if shuffle:
            self.shuffle(p)
        self.say(f'{pl.name} buscou {", ".join(c.name for c in chosen)}' if chosen else
                 f'{pl.name} não pegou nada na busca')
        return chosen

    def discard_from_hand(self, p, n, hint='discard', text='Descarte', source=None, pred=None, min_n=None):
        pl = self.players[p]
        cands = [c for c in pl.hand if pred is None or pred(c)]
        chosen = yield from self.choose_cards(p, cands, n, n if min_n is None else min_n, hint, text, source)
        for c in chosen:
            pl.hand.remove(c)
            pl.discard.append(c)
        if chosen:
            self.say(f'{pl.name} descartou {", ".join(c.name for c in chosen)}')
        return chosen

    # ------------------------------------------------------------- fluxo
    def _flow(self):
        try:
            yield from self._setup()
            while True:
                yield from self._turn()
        except GameOver as e:
            self.winner = e.winner
            self.end_reason = e.reason
            self.done = True
            who = 'Empate' if e.winner == -1 else f'{self.players[e.winner].name} venceu'
            self.say(f'Fim de jogo — {who} ({e.reason})', 'end')

    def _setup(self):
        for p in (0, 1):
            pl = self.players[p]
            self.shuffle(p)
            while True:
                self.draw(p, 7)
                if any(self.playable_basic(c) for c in pl.hand):
                    break
                pl.mulligans += 1
                self.say(f'{pl.name} fez mulligan')
                pl.deck.extend(pl.hand)
                pl.hand = []
                self.shuffle(p)
                if pl.mulligans > 30:
                    raise GameOver(1 - p, 'baralho sem Pokémon Básico')
        if self.forced_first is not None:
            self.first_player = self.forced_first
        else:
            w = self.rng.randrange(2)
            self.say(f'{self.players[w].name} venceu o cara ou coroa')
            opt = yield from self.ask(w, 'first', 'Você venceu o cara ou coroa. Quer começar?',
                                      [Option('Começar jogando', True, 'yes'), Option('Jogar em segundo', False, 'no')])
            self.first_player = w if opt.value else 1 - w
        self.players[self.first_player].went_first = True
        for p in (0, 1):
            pl = self.players[p]
            basics = [c for c in pl.hand if self.playable_basic(c) or self.setup_active_ok(c)]
            seen, opts = set(), []
            for c in basics:
                if c.d.id not in seen:
                    seen.add(c.d.id)
                    opts.append(Option(c.name, c, 'card', card=c))
            opt = yield from self.ask(p, 'setup_active', 'Escolha seu Pokémon Ativo', opts)
            pl.hand.remove(opt.value)
            pl.active = PokemonSlot(opt.value, 0)
            rest = [c for c in pl.hand if self.playable_basic(c)]
            bench = yield from self.choose_cards(p, rest, DEFAULT_BENCH, 0, 'setup_bench', 'Pokémon para o Banco')
            for c in bench:
                pl.hand.remove(c)
                pl.bench.append(PokemonSlot(c, 0))
        for p in (0, 1):
            extra = self.players[1 - p].mulligans
            if extra:
                n = self.draw(p, extra)
                self.say(f'{self.players[p].name} comprou {n} carta(s) extra pelos mulligans do oponente')
        for p in (0, 1):
            pl = self.players[p]
            pl.prizes = [pl.deck.pop(0) for _ in range(min(6, len(pl.deck)))]
        self.setup_done = True
        self.current = self.first_player
        self.say(f'{self.players[self.first_player].name} começa')

    def _turn(self):
        p = self.current
        self.turn += 1
        if self.turn > self.MAX_TURNS:
            raise GameOver(-1, 'limite de turnos')
        pl = self.players[p]
        pl.reset_turn()
        pl.turns_taken += 1
        self.turn_ended = False
        self.say(f'Turno {self.turn} — {pl.name}', 'turn')
        if not pl.deck:
            raise GameOver(1 - p, f'{pl.name} não conseguiu comprar carta')
        self.draw(p, 1)
        yield from self._main_phase(p)
        yield from self.emit('turn_end', player=p)
        yield from self._resolve_kos()
        self.effects = [e for e in self.effects if e.expires > self.turn]
        yield from self._checkup()
        self.current = 1 - p

    def _main_phase(self, p):
        while not self.turn_ended:
            opts = self._main_options(p)
            opt = yield Prompt(p, 'main', 'Escolha uma ação', opts)
            if opt.kind == 'noop':      # Game.refresh(): recalcula as opções após mudar o estado
                continue
            if opt.kind == 'end':
                self.say(f'{self.players[p].name} passou o turno')
                return
            if opt.kind == 'attack':
                att = self.players[p].active
                yield from self._attack(p, opt.value)
                if att is not None and att is self.players[p].active and self.players[1 - p].active is not None \
                        and self.anyhook('attack_twice', slot=att):
                    again = [Option(f'Atacar de novo: {a.name}', a, 'attack', card=att.top, attack=i)
                             for i, a in enumerate(self.attacks_of(att)) if self.can_use_attack(p, a)]
                    if again:
                        o2 = Option('', None, 'noop')
                        while o2.kind == 'noop':
                            o2 = yield Prompt(p, 'main', 'Atacar uma segunda vez?',
                                              again + [Option('Não', None, 'end')])
                        if o2.kind == 'attack':
                            yield from self._attack(p, o2.value)
                return
            yield from self._perform(p, opt)
            yield from self._resolve_kos()
        self.say(f'O turno de {self.players[p].name} terminou')

    # --------------------------------------------------------- ações legais
    def can_play_card(self, p, card) -> bool:
        return self.allowed('can_play', player=p, card=card)

    def can_play_trainer(self, p, c) -> bool:
        pl, d = self.players[p], c.d
        im = d.impl
        if im is None:
            return False
        if d.subtype == 'supporter':
            if pl.supporter_played:
                return False
            if self.turn <= 1 and not im.first_turn_ok:
                return False
        if d.subtype == 'stadium':
            if pl.stadium_played or (self.stadium is not None and self.stadium.name == d.name):
                return False
        if d.as_pokemon and self.bench_space(p) <= 0:
            return False
        if not self.can_play_card(p, c):
            return False
        return im.can_play is None or bool(im.can_play(self, p, c))

    def can_evolve(self, p, slot, card) -> bool:
        d = card.d
        if not d.is_evolution:
            return False
        frm = self.fold('evolves_from', {d.evolves_from}, slot=slot, card=card)
        if slot.name not in frm:
            return False
        if not self.allowed('can_evolve', player=p, slot=slot, card=card):
            return False
        early = self.anyhook('can_evolve_early', slot=slot, card=card)
        if not early:
            if self.first_turn(p) or slot.turn_entered >= self.turn:
                return False
        if slot.turn_evolved >= self.turn and not early:
            return False
        return True

    def can_retreat(self, p) -> bool:
        pl = self.players[p]
        act = pl.active
        if act is None or not pl.bench or pl.retreated:
            return False
        if act.conditions & {'asleep', 'paralyzed'} or act.d.as_pokemon:
            return False
        if not self.allowed('can_retreat', slot=act):
            return False
        return self.energy_count(act) >= self.retreat_cost(act) or self.retreat_cost(act) == 0

    def can_use_attack(self, p, atk) -> bool:
        pl = self.players[p]
        act = pl.active
        if act is None or act.conditions & {'asleep', 'paralyzed'}:
            return False
        if self.turn <= 1 and not (getattr(atk.impl, 'first_turn', False)) and \
                not self.anyhook('first_turn_attack', slot=act):
            return False
        if not self.allowed('can_attack', slot=act, attack=atk):
            return False
        if not self.can_pay(act, self.attack_cost(act, atk)):
            return False
        return atk.impl is None or atk.impl.can_use is None or bool(atk.impl.can_use(self, act))

    def can_use_ability(self, p, s, ab) -> bool:
        im = ab.impl
        if im is None or im.kind != 'activated' or im.run is None:
            return False
        if im.once_per_turn and s.ability_turns.get(ab.name) == self.turn:
            return False
        if im.shared_key and im.shared_key in self.players[p].ability_keys:
            return False
        if not self.ability_active(s, ab):
            return False
        return im.can_use is None or bool(im.can_use(self, p, s))

    def can_attach_energy(self, p, card, slot) -> bool:
        im = card.d.impl
        if im is not None and im.can_attach is not None and not im.can_attach(self, p, card, slot):
            return False
        return self.allowed('can_attach', player=p, card=card, slot=slot)

    def _main_options(self, p) -> list:
        pl = self.players[p]
        opts, seen = [], set()

        def add(key, opt):
            if key not in seen:
                seen.add(key)
                opts.append(opt)

        for c in pl.hand:
            d = c.d
            if d.kind == 'pokemon':
                if d.stage == 0:
                    if self.playable_basic(c) and self.bench_space(p) > 0 and self.can_play_card(p, c):
                        add(('pb', d.id), Option(f'Jogar {d.name} no Banco', c, 'play_basic', card=c))
                else:
                    for s in pl.in_play():
                        if self.can_evolve(p, s, c) and self.can_play_card(p, c):
                            add(('ev', d.id, s.sid), Option(f'Evoluir {self.slot_label(s)} → {d.name}', (c, s),
                                                            'evolve', card=c, target=(p, self.slot_pos(s))))
                for ab in d.abilities:       # Habilidades usáveis da mão (ex.: Emergency Rotation)
                    im = ab.impl
                    if im is not None and im.kind == 'hand' and f'{ab.name}:{c.uid}' not in pl.ability_keys and \
                            self.ability_active_in_hand(c, ab) and (im.can_use is None or im.can_use(self, p, c)):
                        add(('hab', c.uid, ab.name), Option(f'Habilidade {ab.name} — {d.name} (mão)', (c, ab),
                                                            'ability', card=c))
            elif d.kind == 'energy':
                if pl.energy_attached < 1:
                    for s in pl.in_play():
                        if self.can_attach_energy(p, c, s):
                            add(('at', d.id, s.sid), Option(f'Ligar {d.name} em {self.slot_label(s)}', (c, s),
                                                            'attach', card=c, target=(p, self.slot_pos(s))))
            elif d.subtype == 'tool':
                if d.impl is None or not self.can_play_card(p, c):
                    continue
                for s in pl.in_play():
                    if len(s.tools) < self.tool_slots(s) and \
                            (d.impl.can_attach is None or d.impl.can_attach(self, p, c, s)) and \
                            (d.impl.can_play is None or d.impl.can_play(self, p, c)):
                        add(('tl', d.id, s.sid), Option(f'Ligar {d.name} em {self.slot_label(s)}', (c, s),
                                                        'tool', card=c, target=(p, self.slot_pos(s))))
            elif d.kind == 'trainer' and self.can_play_trainer(p, c):
                add(('tr', d.id), Option(f'Jogar {d.name}', c, 'trainer', card=c))

        for s in pl.in_play():
            for ab in s.d.abilities:
                if self.can_use_ability(p, s, ab):
                    add(('ab', s.sid, ab.name), Option(f'Habilidade {ab.name} — {self.slot_label(s)}', (s, ab),
                                                       'ability', card=s.top, target=(p, self.slot_pos(s))))
            if s.d.as_pokemon:
                add(('fd', s.sid), Option(f'Descartar {self.slot_label(s)} do jogo', s, 'discard_fossil',
                                          card=s.top, target=(p, self.slot_pos(s))))

        st = self.stadium
        if st is not None and st.d.impl is not None and st.d.impl.action and not pl.stadium_used and \
                (st.d.impl.action_can is None or st.d.impl.action_can(self, p)):
            add(('st',), Option(f'Usar Estádio {st.name}', st, 'stadium', card=st))

        if self.can_retreat(p):
            for s in pl.bench:
                add(('rt', s.sid), Option(f'Recuar para {self.slot_label(s)}', s, 'retreat',
                                          card=s.top, target=(p, self.slot_pos(s))))

        if pl.active is not None:
            for i, a in enumerate(self.attacks_of(pl.active)):
                if self.can_use_attack(p, a):
                    add(('ak', a.name, a.owner_name), Option(f'Atacar: {a.name}', a, 'attack', card=pl.active.top,
                                                            attack=i))
        opts.append(Option('Passar o turno', None, 'end'))
        return opts

    # ------------------------------------------------------------ execução
    def _perform(self, p, opt):
        pl = self.players[p]
        k = opt.kind
        if k == 'play_basic':
            pl.hand.remove(opt.value)
            yield from self.play_to_bench(p, opt.value, from_hand=True)
        elif k == 'evolve':
            c, s = opt.value
            pl.hand.remove(c)
            yield from self.evolve(p, s, c, from_hand=True)
        elif k == 'attach':
            c, s = opt.value
            pl.hand.remove(c)
            pl.energy_attached += 1
            yield from self.attach_energy(p, c, s, from_hand=True)
        elif k == 'tool':
            c, s = opt.value
            pl.hand.remove(c)
            s.tools.append(c)
            self.say(f'{pl.name} ligou {c.name} em {self.slot_label(s)}')
            yield from self.emit('trainer_played', player=p, card=c)
        elif k == 'trainer':
            yield from self.play_trainer(p, opt.value)
        elif k == 'ability':
            s, ab = opt.value
            if isinstance(s, Card):      # Habilidade usada da mão (ex.: Emergency Rotation)
                pl.ability_keys.add(f'{ab.name}:{s.uid}')
                self.say(f'{pl.name} usou {ab.name} ({s.name}, da mão)', 'ability')
                yield from run(ab.impl.run(self, p, s))
            else:
                yield from self.use_ability(p, s, ab)
        elif k == 'stadium':
            pl.stadium_used = True
            self.say(f'{pl.name} usou o Estádio {self.stadium.name}')
            yield from run(self.stadium.d.impl.action(self, p))
        elif k == 'retreat':
            yield from self.retreat(p, opt.value)
        elif k == 'discard_fossil':
            self.say(f'{pl.name} descartou {opt.value.name} do jogo')
            self.remove_slot(opt.value, to='discard')
            yield from self._promote_if_needed()

    def ability_active_in_hand(self, card, ab) -> bool:
        return True

    def use_ability(self, p, s, ab):
        pl = self.players[p]
        s.ability_turns[ab.name] = self.turn
        if ab.impl.shared_key:
            pl.ability_keys.add(ab.impl.shared_key)
        self.say(f'{pl.name} usou {ab.name} ({s.name})', 'ability')
        yield from run(ab.impl.run(self, p, s))

    def play_to_bench(self, p, card, from_hand=False):
        pl = self.players[p]
        s = PokemonSlot(card, self.turn)
        pl.bench.append(s)
        self.say(f'{pl.name} colocou {card.name} no Banco')
        yield from self.emit('bench_played', player=p, slot=s, from_hand=from_hand)
        if from_hand:
            for ab in card.d.abilities:
                im = ab.impl
                if im is not None and im.kind == 'on_bench' and self.ability_active(s, ab) and \
                        (im.can_use is None or im.can_use(self, p, s)) and \
                        not (im.shared_key and im.shared_key in pl.ability_keys):
                    if (yield from self.yes_no(p, f'Usar a Habilidade {ab.name}?', source=card)):
                        if im.shared_key:
                            pl.ability_keys.add(im.shared_key)
                        s.ability_turns[ab.name] = self.turn
                        self.say(f'{pl.name} usou {ab.name}', 'ability')
                        yield from run(im.run(self, p, s))
        return s

    def evolve(self, p, slot, card, from_hand=True):
        pl = self.players[p]
        old = slot.name
        slot.cards.append(card)
        slot.turn_evolved = self.turn
        keep = 'confused' in slot.conditions and self.anyhook('keep_confusion', slot=slot)
        slot.clear_conditions()
        if keep:
            slot.conditions.add('confused')
        self._slot_left(slot, evolved=True)
        self.say(f'{pl.name} evoluiu {old} para {card.name}')
        yield from self.emit('evolved', player=p, slot=slot, from_hand=from_hand)
        if from_hand:
            for ab in card.d.abilities:
                im = ab.impl
                if im is not None and im.kind == 'on_evolve' and self.ability_active(slot, ab) and \
                        (im.can_use is None or im.can_use(self, p, slot)) and \
                        not (im.shared_key and im.shared_key in pl.ability_keys):
                    if (yield from self.yes_no(p, f'Usar a Habilidade {ab.name}?', source=card)):
                        if im.shared_key:
                            pl.ability_keys.add(im.shared_key)
                        slot.ability_turns[ab.name] = self.turn
                        self.say(f'{pl.name} usou {ab.name}', 'ability')
                        yield from run(im.run(self, p, slot))

    def devolve(self, slot, to='hand'):
        """Remove a carta de evolução do topo (para a mão do dono por padrão)."""
        if not slot.evolved:
            return None
        c = slot.cards.pop()
        (self.players[c.owner].hand if to == 'hand' else self.players[c.owner].discard).append(c)
        keep = 'confused' in slot.conditions and self.anyhook('keep_confusion', slot=slot)
        slot.clear_conditions()
        if keep:
            slot.conditions.add('confused')
        self._slot_left(slot)
        return c

    def attach_energy(self, p, card, slot, from_hand=False, source=None):
        pl = self.players[p]
        slot.energy.append(card)
        self.say(f'{pl.name} ligou {card.name} em {self.slot_label(slot)}')
        im = card.d.impl
        if im is not None and im.on_attach is not None:
            yield from run(im.on_attach(self, p, card, slot, from_hand))
        yield from self.emit('energy_attached', player=p, card=card, slot=slot, from_hand=from_hand)

    def discard_stadium(self):
        """Descarta o Estádio em jogo (dispara o efeito 'quando sair de jogo')."""
        old = self.stadium
        if old is None:
            return
        self.stadium = None
        self.players[old.owner].discard.append(old)
        self.say(f'{old.name} foi descartado')
        if old.d.impl is not None and 'leave' in old.d.impl.events:
            yield from run(old.d.impl.events['leave'](self, Src('stadium', old.owner, old)))

    def play_trainer(self, p, c):
        pl, d = self.players[p], c.d
        pl.hand.remove(c)
        if self.anyhook('trainer_fizzle', player=p, card=c):
            self.say(f'{pl.name} jogou {c.name}, mas a carta foi descartada (moeda)', 'trainer')
            pl.discard.append(c)
            return
        self.say(f'{pl.name} jogou {c.name}', 'trainer')
        pl.played.append(d.name)
        if d.subtype == 'supporter':
            pl.supporter_played = True
        if d.subtype == 'stadium':
            pl.stadium_played = True
            pl.limbo.append(c)
            yield from self.discard_stadium()
            pl.limbo.remove(c)
            self.stadium = c
            yield from self.emit('trainer_played', player=p, card=c)
            return
        if d.as_pokemon:
            s = PokemonSlot(c, self.turn)
            pl.bench.append(s)
            self.say(f'{c.name} entrou no Banco como Pokémon')
            yield from self.emit('bench_played', player=p, slot=s, from_hand=True)
            return
        pl.limbo.append(c)
        if d.impl is not None and d.impl.run is not None:
            yield from run(d.impl.run(self, p, c))
        if c in pl.limbo:      # alguns efeitos movem a própria carta (ex.: Caretaker)
            pl.limbo.remove(c)
            pl.discard.append(c)
        yield from self.emit('trainer_played', player=p, card=c)

    def retreat(self, p, target):
        pl = self.players[p]
        act = pl.active
        cost = self.retreat_cost(act)
        if self.anyhook('retreat_fizzle', player=p, slot=act):
            pl.retreated = True
            self.say(f'{pl.name} tentou recuar {act.name}, mas o recuo falhou (moeda)')
            return
        if cost > 0:
            paid = yield from self.choose_energy_to_discard(p, act, cost, 'retreat_energy',
                                                            'Energia para pagar o recuo')
            for e in paid:
                act.energy.remove(e)
                pl.discard.append(e)
        pl.retreated = True
        self.say(f'{pl.name} recuou {act.name} para {target.name}')
        yield from self.switch_active(p, target)

    def choose_energy_to_discard(self, p, slot, units_needed, hint='discard_energy', text='Descartar Energia',
                                 source=None, pred=None):
        """Escolhe cartas de Energia cujas unidades somem pelo menos `units_needed`."""
        eu = [(e, u) for e, u in self.energy_units(slot) if pred is None or pred(e)]
        total = sum(len(u) for _, u in eu)
        if total <= units_needed:
            return [e for e, _ in eu]
        kinds = {e.d.id for e, _ in eu}
        if len(kinds) == 1 and all(len(u) == 1 for _, u in eu):
            return [e for e, _ in eu][:units_needed]
        chosen, got = [], 0
        while got < units_needed:
            pool = [e for e, _ in eu if e not in chosen]
            pick = yield from self.choose_cards(p, pool, 1, 1, hint, text, source)
            chosen.append(pick[0])
            got += len(dict(eu)[pick[0]])
        return chosen

    def switch_active(self, p, bench_slot, cause='switch'):
        """Troca o Ativo de p pelo Pokémon do Banco (dispara moved_to_bench/moved_to_active)."""
        pl = self.players[p]
        i = pl.bench.index(bench_slot)
        old = pl.active
        if old is not None:
            old.clear_conditions()
            self._slot_left(old)
            pl.bench[i] = old
        else:
            pl.bench.pop(i)
        pl.active = bench_slot
        if old is not None:
            yield from self.emit('moved_to_bench', player=p, slot=old, cause=cause)
        yield from self.emit('moved_to_active', player=p, slot=bench_slot, cause=cause)

    def remove_slot(self, slot, to='discard'):
        """Tira um Pokémon de jogo; todas as cartas vão para `to` (discard/hand/deck)."""
        p = slot.owner
        pl = self.players[p]
        if to == 'hand' and self.anyhook('no_return_to_hand', slot=slot):
            return []
        if pl.active is slot:
            pl.active = None
        elif slot in pl.bench:
            pl.bench.remove(slot)
        self._slot_left(slot)
        self.effects = [e for e in self.effects if e.target is not slot]
        cards = slot.all_cards()
        for c in cards:
            dest = {'discard': self.players[c.owner].discard, 'hand': self.players[c.owner].hand,
                    'deck': self.players[c.owner].deck, 'lost': self.players[c.owner].lost_zone}[to]
            dest.append(c)
        if to == 'deck':
            self.shuffle(p)
        return cards

    def _promote_if_needed(self):
        for o in (1 - self.current, self.current):
            pl = self.players[o]
            if pl.active is None and pl.bench:
                s = yield from self.choose_slot(o, pl.bench, 'promote', 'Escolha seu novo Pokémon Ativo')
                pl.bench.remove(s)
                pl.active = s
                self.say(f'{pl.name} promoveu {s.name} a Ativo')
                yield from self.emit('moved_to_active', player=o, slot=s, cause='promote')
        self._check_win()

    # ------------------------------------------------------------- ataque
    def _attack(self, p, atk):
        pl, op = self.players[p], self.players[1 - p]
        att = pl.active
        self.say(f'{att.name} usou {atk.name}', 'attack')
        # rulings 2317/2326: Smokescreen/Sand Attack vem antes da moeda da Confusão
        smoke = [e.data.get('flips', 1) for e in self.effects if e.target is att and e.data.get('smokescreen')]
        if smoke and self.flips(max(smoke)) < max(smoke):
            self.say(f'O ataque de {att.name} não aconteceu')
            return
        if 'confused' in att.conditions and not self.flip():
            att.damage += 10 * att.flags.get('confused_n', 3)
            self.say(f'{att.name} está Confuso e se feriu (3 contadores)')
            yield from self._resolve_kos()
            return
        att.flags.setdefault('atk_log', []).append((self.turn, atk.name))
        pl.attack_log.append((self.turn, att, atk.name))
        ctx = AttackCtx(self, p, att, op.active, atk)
        ctx.queue = []
        self._actx = ctx
        im = atk.impl
        try:
            if im is not None and im.run is not None:
                yield from run(im.run(self, ctx))
            else:
                if im is not None and im.pre is not None:
                    yield from run(im.pre(self, ctx))
                if not ctx.no_damage:
                    yield from self.main_damage(ctx)
                if im is not None and im.post is not None and not ctx.no_damage:
                    yield from run(im.post(self, ctx))
                for f in ctx.data.pop('after', []):      # remoções de Energia adiadas (ataque que não chegou ao 'post')
                    f()
            from .effects.energies import RETURNERS
            for e in ctx.discarded_energy:
                if e.name in RETURNERS:
                    RETURNERS[e.name](self, e, ctx)
            for ev, target, dmg in ctx.queue:
                yield from self.emit('damaged_by_attack', ctx=ctx, slot=target, damage=dmg)
            yield from self.emit('after_attack', ctx=ctx)
            yield from self._resolve_kos()
        finally:
            self._actx = None

    def main_damage(self, ctx):
        """Causa o dano principal do ataque ao Pokémon Ativo do oponente."""
        if False:
            yield
        d = ctx.defender
        if ctx.damage > 0 and d is not None and self.in_play(d):
            self.deal_attack_damage(ctx, d, ctx.damage)

    def calc_damage(self, ctx, target, base) -> int:
        if base <= 0:
            return 0
        active_target = target.owner == ctx.opp and self.players[ctx.opp].active is target
        dmg = base
        if active_target:
            dmg = self.fold('damage_out', dmg, ctx=ctx, target=target)
            if not ctx.ignore_weakness:
                w, mult = self.weakness(target)
                if w and w in self.types(ctx.attacker):
                    dmg *= mult
            if not ctx.ignore_resistance and target.d.resistance and target.d.resistance in self.types(ctx.attacker):
                dmg -= target.d.resistance_value
        if not self.is_active(target) and 'tera' in target.d.tags:
            return 0
        if not active_target and target.owner == ctx.opp:
            dmg = self.fold('damage_out_bench', dmg, ctx=ctx, target=target)     # ex.: Gloomy Garbage (ruling 2345)
        if dmg > 0:
            if (ctx.ignore_effects or self.anyhook('ignore_effects', ctx=ctx)) and target.owner == ctx.opp:
                dmg = self.fold('damage_in', dmg, ctx=ctx, target=target, active=active_target,
                                _skip_target=target)
            else:
                dmg = self.fold('damage_in', dmg, ctx=ctx, target=target, active=active_target)
        return max(0, dmg)

    def deal_attack_damage(self, ctx, target, base) -> int:
        dmg = self.calc_damage(ctx, target, base)
        if dmg <= 0:
            return 0
        if dmg >= self.hp_left(target) and self.anyhook('survive', slot=target, damage=dmg, ctx=ctx):
            dmg = max(0, self.hp_left(target) - 10)
            self.say(f'{target.name} resistiu com 10 HP!')
        target.damage += dmg
        target.flags['hit'] = (self.turn, 'attack', ctx.attacker)
        target.flags.setdefault('dmg_log', []).append((self.turn, dmg))
        ctx.queue.append(('damaged', target, dmg))
        if target is ctx.defender:
            ctx.done_damage += dmg
        self.say(f'{ctx.attacker.name} causou {dmg} de dano em {self.slot_label(target)}', 'damage')
        return dmg

    def effects_prevented(self, ctx, target) -> bool:
        """Efeitos do ataque em `target` (do oponente) estão prevenidos?"""
        if ctx is None or target.owner == ctx.player:
            return False
        return self.anyhook('prevent_attack_effects', ctx=ctx, target=target)

    def effects_prevented_from(self, player, attacker, target) -> bool:
        """Como `effects_prevented`, mas para efeito atrasado de um ataque anterior (sem o ctx original):
        `player`/`attacker` são quem usou o ataque (ruling 2408: Mist Energy bloqueia o Shellnado Spin)."""
        from types import SimpleNamespace
        return self.effects_prevented(SimpleNamespace(player=player, opp=1 - player, attacker=attacker,
                                                      ignore_effects=False), target)

    def place_counters(self, target, n, kind='attack', by=None, ctx=None) -> int:
        """Coloca n contadores de dano (sem fraqueza/resistência). kind: attack|ability|trainer|other."""
        if n <= 0:
            return 0
        by = by if by is not None else (ctx.player if ctx is not None else None)
        if kind == 'attack' and ctx is not None and self.effects_prevented(ctx, target):
            return 0
        if self.anyhook('prevent_counters', target=target, kind=kind, by=by):
            return 0
        target.damage += 10 * n
        if kind == 'attack':
            target.flags['hit'] = (self.turn, 'attack', ctx.attacker if ctx else None)
        self.say(f'{n} contador(es) de dano em {self.slot_label(target)}', 'damage')
        return n

    def heal(self, slot, n) -> int:
        if slot.damage <= 0 or not self.allowed('can_heal', slot=slot):
            return 0
        h = min(slot.damage, n)
        slot.damage -= h
        if h:
            slot.flags['healed_turn'] = self.turn      # ruling 2405: ataques tipo Lively Cutter
            self.say(f'{self.slot_label(slot)} recuperou {h}')
        return h

    def add_condition(self, slot, cond, ctx=None) -> bool:
        if slot is None or not self.in_play(slot):
            return False
        if ctx is not None and self.effects_prevented(ctx, slot):
            return False
        if slot.d.as_pokemon or self.anyhook('condition_immune', slot=slot, cond=cond):
            return False
        if cond in EXCLUSIVE_CONDITIONS:
            slot.conditions -= EXCLUSIVE_CONDITIONS
        if cond not in slot.conditions:
            slot.flags.pop({'poisoned': 'poison_n', 'confused': 'confused_n'}.get(cond, ''), None)
        slot.conditions.add(cond)
        if cond == 'paralyzed':
            slot.paralyzed_until = self.turn + (2 if self.current == slot.owner else 1)
        self.say(f'{self.slot_label(slot)} agora está {self._cond_pt(cond)}')
        return True

    @staticmethod
    def _cond_pt(c):
        return {'asleep': 'Adormecido', 'paralyzed': 'Paralisado', 'confused': 'Confuso',
                'poisoned': 'Envenenado', 'burned': 'Queimado'}[c]

    def discard_energy(self, slot, cards, ctx=None):
        """Descarta energias de um Pokémon (registra no ctx do ataque)."""
        out = []
        for e in cards:
            if e in slot.energy:
                slot.energy.remove(e)
                self.players[e.owner].discard.append(e)
                out.append(e)
        if ctx is not None and slot is ctx.attacker:
            ctx.discarded_energy += out
        if out:
            self.say(f'Descartou {", ".join(e.name for e in out)} de {self.slot_label(slot)}')
        return out

    def estimate_attack(self, slot, atk, target=None) -> int:
        im = atk.impl
        try:
            base = im.estimate(self, slot, target) if (im and im.estimate) else atk.damage
        except Exception:
            base = atk.damage
        if target is None:
            return base
        ctx = AttackCtx(self, slot.owner, slot, target, atk)
        try:
            return self.calc_damage(ctx, target, base)
        except Exception:
            return base

    # ---------------------------------------------------- checkup, KO, vitória
    def _checkup(self):
        for p in (self.current, 1 - self.current):
            s = self.players[p].active
            if s is None:
                continue
            if 'poisoned' in s.conditions:
                n = self.fold('checkup_counters', s.flags.get('poison_n', 1), slot=s, cond='poisoned')
                s.damage += 10 * n
                self.say(f'{s.name} sofreu {n * 10} de Veneno')
            if 'burned' in s.conditions:
                n = self.fold('checkup_counters', 2, slot=s, cond='burned')
                s.damage += 10 * n
                self.say(f'{s.name} sofreu {n * 10} de Queimadura')
                if self.flip():
                    s.conditions.discard('burned')
            if 'asleep' in s.conditions:
                if self.flip():
                    s.conditions.discard('asleep')
                    self.say(f'{s.name} acordou')
                else:
                    s.flags['stayed_asleep'] = self.turn
            if 'paralyzed' in s.conditions and s.paralyzed_until <= self.turn:
                s.conditions.discard('paralyzed')
                s.paralyzed_until = -1
        yield from self.emit('checkup')
        yield from self._resolve_kos()

    def _resolve_kos(self):
        while True:
            kod = [s for o in (0, 1) for s in self.players[o].in_play() if s.damage >= self.hp(s)]
            if not kod:
                break
            owed = [0, 0]
            labels = {s.sid: self.slot_label(s) for s in kod}
            for s in kod:
                o = s.owner
                hit = s.flags.get('hit')
                by_attack = bool(hit and hit[0] == self.turn and hit[1] == 'attack' and o != self.current)
                attacker = hit[2] if by_attack else None
                n = self.fold('prizes', s.d.base_prizes, slot=s, taker=1 - o, by_attack=by_attack,
                              attacker=attacker)
                dest = {'to': 'discard', 'redirect': {}}
                yield from self.emit('knocked_out', slot=s, owner=o, by_attack=by_attack, attacker=attacker,
                                     dest=dest)
                self.say(f'{labels[s.sid]} foi Nocauteado!', 'ko')
                self.ko_log.append({'turn': self.turn, 'owner': o, 'name': s.name, 'by_attack': by_attack,
                                    'family': s.d.family, 'tags': set(s.d.tags)})
                pl = self.players[o]
                if pl.active is s:
                    pl.active = None
                elif s in pl.bench:
                    pl.bench.remove(s)
                self._slot_left(s)
                self.effects = [e for e in self.effects if e.target is not s]
                for c in s.all_cards():
                    where = dest['redirect'].get(c.uid, 'hand' if (dest['to'] == 'hand' and c in s.cards)
                                                 else 'discard')
                    {'discard': self.players[c.owner].discard, 'hand': self.players[c.owner].hand,
                     'deck': self.players[c.owner].deck}[where].append(c)
                owed[1 - o] += max(0, n)
            for t in (0, 1):
                if owed[t]:
                    self.take_prizes(t, owed[t])
            self._check_win()
        yield from self._promote_if_needed()

    def take_prizes(self, t, n):
        pl = self.players[t]
        n = min(n, len(pl.prizes))
        self.prize_log.append((self.turn, t, n))
        for _ in range(n):
            pl.hand.append(pl.prizes.pop(0))
        self.say(f'{pl.name} pegou {n} carta(s) de prêmio ({len(pl.prizes)} restantes)', 'prize')

    def _check_win(self):
        win = [False, False]
        reasons = ['', '']
        if not self.setup_done:
            return
        for i in (0, 1):
            if not self.players[i].prizes:
                win[i], reasons[i] = True, 'pegou todos os prêmios'
            if not self.players[1 - i].in_play():
                win[i], reasons[i] = True, 'oponente sem Pokémon em jogo'
        if win[0] and win[1]:
            raise GameOver(-1, 'ambos cumpriram condição de vitória')
        for i in (0, 1):
            if win[i]:
                raise GameOver(i, reasons[i])
