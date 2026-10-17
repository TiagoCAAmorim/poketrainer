"""Reprodução de partidas do Pokémon TCG Live dentro do motor.

O motor joga a partida; a cada decisão, o reprodutor escolhe a opção que corresponde à linha do
log. Cartas que o log não revela (mão e baralho do oponente, prêmios) começam como "carta oculta"
e assumem a identidade correta no momento em que o log as mostra. Moedas, compras, buscas e
prêmios são forçados a seguir o log.

Resultado: até onde a partida foi reproduzida, a primeira divergência (se houver) e as diferenças
de dano entre o log oficial e o motor — ou seja, uma checagem jogada a jogada das regras.

    rep = replay_log(open('partida.log').read())
    print(rep.summary())
"""
from __future__ import annotations

from collections import Counter
import re
from dataclasses import dataclass, field

from ..carddb import db
from ..core import Card, CardDef, Option, TrainerImpl
from ..engine import Game
from .parse import Event, parse_log

UNKNOWN_ID = 'UNKNOWN'
CONSEQUENCE_KEYS = {
    'blog_loc_knockout', 'blog_loc_took_single_prize_card', 'blog_loc_took_prize_cards', 'blog_loc_added_prize',
    'blog_loc_promote_to_active', 'blog_loc_discarded_attachment', 'blog_loc_discarded_attachment_multi',
    'blog_loc_coin_flip_single', 'blog_loc_coin_flip_multi', 'blog_loc_special_condition', 'blog_loc_remove_condition',
    'blog_loc_condition_damage_single', 'blog_loc_condition_damage_many', 'blog_loc_secondary_damage',
    'blog_loc_secondary_weak_attack', 'blog_loc_secondary_resistance_attack', 'blog_loc_secondary_weak_and_resistant',
    'blog_loc_damage_blocked', 'blog_loc_effect_prevention_damage', 'blog_loc_healed', 'blog_loc_healed_dc',
    'blog_loc_player_placed_dc', 'blog_loc_player_placed_single_dc', 'blog_loc_shuffled_deck', 'blog_loc_shuffled_fallback',
    'blog_loc_remove_all_effects', 'blog_loc_tera_effect', 'blog_loc_selected_option', 'blog_loc_reconnect',
    'blog_loc_card_activated', 'blog_loc_oncepergame_used', 'blog_loc_discarded_from_board',
    'blog_loc_move_to_discard', 'blog_loc_switched_active', 'blog_loc_drew_card', 'blog_loc_timeout',
}
ATTACK_KEYS = {'blog_loc_applied_damage', 'blog_loc_weak_attack', 'blog_loc_resistant_attack',
               'blog_loc_weak_and_resistant_attack'}
NUM_WORD = re.compile(r'^(\d+) cards?$|^a card$|^another card$|^A card$')


def unknown_def():
    D = db()
    if UNKNOWN_ID not in D.cards:
        d = CardDef(id=UNKNOWN_ID, name='(carta oculta)', kind='trainer', subtype='item',
                    impl=TrainerImpl(can_play=lambda g, p, c: False))
        d.idx = 0
        D.cards[UNKNOWN_ID] = d
    return D.cards[UNKNOWN_ID]


class Desync(Exception):
    pass


@dataclass
class ReplayReport:
    players: list
    actions_total: int = 0
    actions_done: int = 0
    turns_total: int = 0
    turns_done: int = 0
    finished: bool = False
    divergence: str | None = None
    damage_checks: list = field(default_factory=list)   # (turno, linha, dano log, dano motor)
    notes: list = field(default_factory=list)
    game: Game | None = None
    samples: list = field(default_factory=list)          # (estado codificado, índice escolhido, jogador)

    def summary(self):
        ok = sum(1 for c in self.damage_checks if c[2] == c[3])
        lines = [f'Jogadores: {" x ".join(self.players)}',
                 f'Ações reproduzidas: {self.actions_done}/{self.actions_total}  '
                 f'(turnos {self.turns_done}/{self.turns_total})',
                 f'Danos conferidos: {ok}/{len(self.damage_checks)} iguais ao log oficial']
        for t, line, a, b in self.damage_checks:
            if a != b:
                lines.append(f'  ✘ turno {t}: log={a} motor={b} — {line}')
        if self.divergence:
            lines.append(f'Divergência: {self.divergence}')
        elif self.finished:
            lines.append('Partida reproduzida até o fim sem divergências.')
        lines += [f'  nota: {n}' for n in self.notes[:20]]
        return '\n'.join(lines)


class ReplayGame(Game):
    def __init__(self, rp, *a, **kw):
        self.rp = rp
        self.manual_main = True
        super().__init__(*a, **kw)

    def shuffle(self, p):
        super().shuffle(p)
        self.rp.after_shuffle(self, p)

    def draw(self, p, n=1):
        self.rp.before_draw(self, p, n)
        return super().draw(p, n)

    def flip(self, who=None):
        r = self.rp.next_flip()
        if r is None:
            return super().flip(who)
        self.say(f'Moeda: {"cara" if r else "coroa"}', 'coin')
        return r

    def take_prizes(self, t, n):
        self.rp.before_prizes(self, t, n)
        super().take_prizes(t, n)

    def _turn(self):
        self.rp.on_turn_start(self, self.current, self.turn + 1)
        yield from super()._turn()


class Replayer:
    def __init__(self, log, record=False):
        self.log = log
        self.record = record
        self.names = log.players[:2]
        self.D = db()
        self.unk = unknown_def()
        self.pending_draws = {0: [], 1: []}
        self.pending_flips = []
        self.pending_prizes = {0: [], 1: []}
        self.want = []           # nomes desejados nas escolhas da ação atual
        self.slot_used = Counter()  # alvos (por nome) já usados na ação atual
        self.disc_used = Counter()  # Energias descartadas do Pokémon já atribuídas a escolhas
        self.ctx_events = []     # sub-eventos da ação atual
        self.report = ReplayReport(players=self.names)
        self._versions = self._collect_versions()
        setup = log.phases[0] if log.phases and log.phases[0].kind == 'setup' else None
        self.setup = setup
        self.turn_events = [p for p in log.phases if p.kind == 'turn']
        self.report.turns_total = len(self.turn_events)
        self.report.actions_total = sum(1 for t in self.turn_events for e in t.events if self._actionable(e))
        self.cursor = {}         # turno -> índice do próximo evento
        self.frames = None       # lista de quadros (estado após cada jogada) para a interface
        self.forced = {}         # ponto de ambiguidade -> alternativa escolhida (retrocesso)
        self.amb_counter = 0
        self.amb_points = []

    # ------------------------------------------------------------------ utilidades
    def pidx(self, name):
        return self.names.index(name) if name in self.names else None

    def _collect_versions(self):
        """(jogador, carta) -> ataques/habilidades usados no log; jogador -> tipos de Energia usados."""
        used, etypes = {}, {}
        for ph in self.log.phases:
            for e in [x for ev in ph.events for x in [ev] + ev.subs]:
                pl = e.f.get('playerName') or e.f.get('attackingPlayerName')
                if e.key in ATTACK_KEYS or e.key == 'blog_loc_used_attack':
                    nm = e.f.get('attackingPokemonCardName')
                    used.setdefault((pl, nm), set()).add(e.f.get('attackName'))
                if e.key.startswith('blog_loc_attach_card'):
                    ds = self.D.named(e.f.get('sourceCardName', ''))
                    if ds and ds[0].kind == 'energy':
                        t = ds[0].provides or next((x for x in 'GRWLPFDM' if
                                                    {'G': 'Grass', 'R': 'Fire', 'W': 'Water', 'L': 'Lightning',
                                                     'P': 'Psychic', 'F': 'Fighting', 'D': 'Darkness',
                                                     'M': 'Metal'}[x] in ds[0].name), None)
                        if t:
                            etypes.setdefault(pl, {}).setdefault(t, 0)
                            etypes[pl][t] += 1
        self._etypes = etypes
        return used

    def defn(self, name, p=None):
        ds = self.D.named(name)
        if not ds:
            raise Desync(f'carta desconhecida no log: {name!r}')
        if len(ds) == 1:
            return ds[0]
        pname = self.names[p] if p is not None else None
        used = self._versions.get((pname, name), set())
        et = getattr(self, '_etypes', {}).get(pname, {})

        def score(d):
            return (len(used & {a.name for a in d.attacks + d.abilities}) * 100 +
                    sum(et.get(t, 0) for t in d.types))
        return max(ds, key=score)

    def morph(self, card, name):
        card.d = self.defn(name, card.owner)

    def ensure_n(self, g, p, zone, names, top=False):
        """Garante a multiplicidade: ['Beldum', 'Beldum'] → duas cartas Beldum na zona."""
        from collections import Counter
        got = []
        for nm, k in Counter(names).items():
            for _ in range(k):
                c = self.ensure_in(g, p, zone, nm, top, exclude=got)
                if c is not None:
                    got.append(c)
        return got

    def ensure_in(self, g, p, zone, name, top=False, exclude=()):
        """Garante uma carta `name` na zona (deck/hand/prizes) do jogador p (morfando cartas ocultas)."""
        pl = g.players[p]
        zones = {'deck': pl.deck, 'hand': pl.hand, 'prizes': pl.prizes}
        z = zones[zone]
        for i, c in enumerate(z):
            if c.d.name == name and c not in exclude:
                if top and zone == 'deck' and i > 0:
                    z.insert(0, z.pop(i))
                return c
        for i, c in enumerate(z):
            if c.d.id == UNKNOWN_ID:
                self.morph(c, name)
                if top and zone == 'deck' and i > 0:
                    z.insert(0, z.pop(i))
                return c
        # troca com uma carta de outra zona oculta
        for oz_name, oz in zones.items():
            if oz is z:
                continue
            for j, c in enumerate(oz):
                if c.d.name == name or c.d.id == UNKNOWN_ID:
                    victim = next((k for k, x in enumerate(z) if x.d.id == UNKNOWN_ID), None)
                    if victim is None:
                        continue
                    z[victim], oz[j] = oz[j], z[victim]
                    if c.d.id == UNKNOWN_ID:
                        self.morph(z[victim], name)
                    if top and zone == 'deck':
                        z.insert(0, z.pop(victim))
                    return z[victim]
        if zone == 'hand':
            # reconciliação: traz a carta do baralho trocando por uma carta da mão (registrado como nota)
            src = next((c for c in pl.deck if c.d.name == name), None) or \
                next((c for c in pl.deck if c.d.id == UNKNOWN_ID), None)
            victim = next((c for c in reversed(pl.hand) if c not in exclude), None)
            if src is not None and victim is not None:
                i, j = pl.deck.index(src), pl.hand.index(victim)
                pl.deck[i], pl.hand[j] = victim, src
                if src.d.id == UNKNOWN_ID:
                    self.morph(src, name)
                self.report.notes.append(f'mão de {pl.name} reconciliada: {victim.name} → {name}')
                self.report.reconciled = getattr(self.report, 'reconciled', 0) + 1
                return src
        self.report.notes.append(f'não foi possível colocar {name} em {zone} de {pl.name}')
        return None

    # ------------------------------------------------------------------ oráculos
    def before_draw(self, g, p, n):
        pl = g.players[p]
        names = self.pending_draws[p][:n]
        self.pending_draws[p] = self.pending_draws[p][n:]
        for i, nm in enumerate(names):
            if i >= len(pl.deck):
                break
            if nm is None:   # compra oculta: preferir carta oculta no topo
                j = next((k for k in range(i, len(pl.deck)) if pl.deck[k].d.id == UNKNOWN_ID), None)
            else:
                c = self.ensure_in(g, p, 'deck', nm)
                j = pl.deck.index(c) if c in pl.deck else None
            if j is not None and j != i:
                pl.deck.insert(i, pl.deck.pop(j))

    def on_turn_start(self, g, p, turn_no):
        t = turn_no - 1
        if not (0 <= t < len(self.turn_events)):
            return
        ev = next((x for x in self.turn_events[t].events if x.key == 'blog_loc_drew_card'), None)
        if ev is None:
            return
        nm = ev.f.get('cardName')
        known = nm if nm and not NUM_WORD.match(nm) else None
        if known:
            self.ensure_in(g, p, 'deck', known)
        self.pending_draws[p] = [known]

    def after_shuffle(self, g, p):
        # cartas que o log diz que serão compradas em seguida ficam no topo
        pass

    def next_flip(self):
        return self.pending_flips.pop(0) if self.pending_flips else None

    def before_prizes(self, g, t, n):
        names = self.pending_prizes[t][:n]
        self.pending_prizes[t] = self.pending_prizes[t][n:]
        pl = g.players[t]
        for i, nm in enumerate(names):
            c = self.ensure_in(g, t, 'prizes', nm)
            if c in pl.prizes:
                pl.prizes.insert(i, pl.prizes.pop(pl.prizes.index(c)))

    # ------------------------------------------------------------------ preparação de uma ação
    def _list(self, e):
        """Nomes de cartas citados por um sub-evento (cardName ou a lista '•')."""
        if e.cards:
            return list(e.cards)
        nm = e.f.get('cardName')
        if nm and not NUM_WORD.match(nm):
            return [nm]
        return []

    def _flips(self, events):
        out = []
        for e in events:
            if e.key == 'blog_loc_coin_flip_single':
                out.append(e.f.get('coinFace') in ('heads', 'cara'))
            elif e.key == 'blog_loc_coin_flip_multi':
                n, k = int(e.f['numCoinFlips']), int(e.f['numCoinMeasured'])
                face = e.f.get('coinFace') in ('heads', 'cara')
                hs = k if face else n - k
                out += [True] * hs + [False] * (n - hs)
        return out

    def _seen_names(self):
        """Cartas que cada jogador comprovadamente usa (eventos principais inequívocos)."""
        if hasattr(self, '_seen'):
            return self._seen
        seen = {0: set(), 1: set()}
        keys = {'blog_loc_played_to_bench', 'blog_loc_play_to_bench', 'blog_loc_played_card', 'blog_loc_played_to_stadium',
                'blog_loc_play_to_active', 'blog_loc_played_to_active'}
        for ph in self.log.phases:
            for e in ph.events:
                q = self.pidx(e.f.get('playerName', ''))
                if q is None:
                    continue
                if e.key in keys:
                    seen[q].add(e.f['cardName'])
                elif e.key.startswith('blog_loc_evolved'):
                    seen[q] |= {e.f['sourcePokemonCardName'], e.f['targetPokemonCardName']}
                elif e.key.startswith('blog_loc_attach_card'):
                    seen[q].add(e.f['sourceCardName'])
                elif e.key == 'blog_loc_draw_opening_hand':
                    seen[q] |= {c for s_ in e.subs for c in s_.cards}
        self._seen = seen
        return seen

    def owner_of_names(self, default, names):
        """O log às vezes atribui ao jogador ativo cartas que são do oponente; decide pelo histórico."""
        if not names:
            return default
        seen = self._seen_names()
        mine = sum(1 for n in names if n in seen[default])
        theirs = sum(1 for n in names if n in seen[1 - default])
        return 1 - default if theirs > mine else default

    def prepare(self, g, p, main, extra=()):
        """Antes de executar uma ação principal: garante cartas e prepara compras/moedas/escolhas."""
        events = list(main.subs) + list(extra)
        self.ctx_events = [main] + events
        self.want = []
        self.disc_used = Counter()
        self.slot_used = Counter()
        attach_names = {}
        self.pending_flips = self._flips([main] + events)
        for e in events:
            who = self.pidx(e.f.get('playerName', '')) if e.f.get('playerName') else p
            who = p if who is None else who
            k = e.key
            names = self._list(e)
            who = self.owner_of_names(who, names)
            if k == 'blog_loc_drew_card':
                cnt = int(e.f['cardName'].split()[0]) if re.match(r'^\d+ cards$', e.f.get('cardName', '')) else 1
                lst = names if names else [None] * cnt
                self.ensure_n(g, who, 'deck', [n for n in lst if n])
                self.pending_draws[who] = list(lst)
                self.want += [n for n in lst if n]
            elif k in ('blog_loc_drew_then_play_bench', 'blog_loc_drew_then_play_bench_multi',
                       'blog_loc_drew_then_play_active', 'blog_loc_drew_then_play_stadium'):
                self.ensure_n(g, who, 'deck', names)
                self.want += names
            elif k in ('blog_loc_discarded_from_board', 'blog_loc_discarded_from_hand') and \
                    (main.key in ATTACK_KEYS or main.key == 'blog_loc_used_attack') and \
                    'from your hand' not in self._move_text(main):
                got = self.ensure_n(g, who, 'deck', names, top=True)      # descartado do topo pelo ataque
                chosen = [x.f.get('selectedOption') for x in events if x.key == 'blog_loc_selected_option']
                for c in got:
                    alt = [d for d in self.D.named(c.d.name) if any(a.name in chosen for a in d.attacks)]
                    if alt and c.d not in alt:
                        c.d = alt[0]
                self.want += names
            elif k in ('blog_loc_shuffled_card_into_deck', 'blog_loc_move_to_bottom_deck'):
                txt = self._move_text(main)
                if 'hand' in txt and 'discard pile' not in txt:
                    self.ensure_n(g, who, 'hand', names)
                self.want += names
            elif k in ('blog_loc_discarded_from_board', 'blog_loc_discarded_from_hand'):
                txt = self._move_text(main)
                if 'discard pile' not in txt or 'from your hand' in txt or 'hand' in txt:
                    self.ensure_n(g, who, 'hand', names)
                self.want += names
            elif k in ('blog_loc_attach_card_active', 'blog_loc_attach_card_bench', 'blog_loc_attach_card_fallback'):
                nm = e.f['sourceCardName']
                attach_names.setdefault(who, []).append(nm)
                self.want.append(nm)
            elif k == 'blog_loc_move_to_hand':
                self.want.append(e.f['cardName'])
            elif k in ('blog_loc_move_to_deck', 'blog_loc_move_on_top_deck'):
                self.want += names
        txt = self._move_text(main)
        for who, names in attach_names.items():
            if 'from your hand' in txt or 'from their hand' in txt:
                self.ensure_n(g, who, 'hand', names)
            elif re.search(r'search your deck|look at the top|cards of your deck|from your deck', txt, re.I) and \
                    'discard pile' not in txt:
                self.ensure_n(g, who, 'deck', names, top=True)
        return events

    def _move_text(self, e):
        """Texto do ataque/habilidade/treinador citado no evento (para saber de onde vêm as cartas)."""
        if e.key in ('blog_loc_played_card', 'blog_loc_played_to_fallback'):
            ds = self.D.named(e.f.get('cardName', ''))
            return ds[0].text if ds else ''
        mon, nm = e.f.get('attackingPokemonCardName'), e.f.get('attackName')
        for d in self.D.named(mon or ''):
            for a in d.attacks + d.abilities:
                if a.name == nm:
                    return a.text
        return ''

    def collect_prizes(self, turn_events, start):
        """Olha os eventos-consequência após a ação para descobrir os prêmios pegos."""
        i = start
        while i < len(turn_events) and not self._actionable(turn_events[i]):
            e = turn_events[i]
            if e.key == 'blog_loc_added_prize' and not NUM_WORD.match(e.f.get('cardName', '')):
                who = self.pidx(e.f['playerName'])
                if who is not None:
                    self.pending_prizes[who].append(e.f['cardName'])
            i += 1

    # ------------------------------------------------------------------ mapeamento
    def _actionable(self, e):
        k = e.key
        if k in CONSEQUENCE_KEYS or e.depth:
            return False
        return k in ATTACK_KEYS or k in {
            'blog_loc_played_to_bench', 'blog_loc_play_to_bench', 'blog_loc_played_card', 'blog_loc_played_to_stadium',
            'blog_loc_played_to_fallback', 'blog_loc_evolved_active', 'blog_loc_evolved_bench', 'blog_loc_evolved_fallback',
            'blog_loc_attach_card_active', 'blog_loc_attach_card_bench', 'blog_loc_attach_card_fallback',
            'blog_loc_used_attack', 'blog_loc_retreated', 'blog_loc_manual_end'}

    def _slot_matches(self, g, slot, name, where):
        if slot is None or slot.name != name:
            return False
        if where == 'active':
            return g.is_active(slot)
        if where == 'bench':
            return not g.is_active(slot)
        return True

    def _where(self, key):
        return 'active' if key.endswith('_active') else ('bench' if key.endswith('_bench') else None)

    def map_main(self, g, p, e, turn_events, idx):
        """Escolhe a opção da fase principal correspondente ao evento e."""
        opts = g.prompt.options
        k, f = e.key, e.f
        pl = g.players[p]
        if k == 'blog_loc_manual_end':
            return self._find(opts, lambda o: o.kind == 'end')
        if k in ('blog_loc_played_to_bench', 'blog_loc_play_to_bench'):
            nm = f['cardName']
            self._ensure_and_refresh(g, p, nm)
            return self._find(g.prompt.options, lambda o: o.kind in ('play_basic', 'trainer') and o.card.name == nm)
        if k in ('blog_loc_played_card', 'blog_loc_played_to_fallback') and g.stadium is not None and \
                g.stadium.name == f['cardName'] and not g.players[p].stadium_used:
            st = self._find(opts, lambda o: o.kind == 'stadium')
            if st is not None:
                return st
        if k in ('blog_loc_played_card', 'blog_loc_played_to_fallback'):
            ds = self.D.named(f['cardName'])
            if ds and ds[0].kind == 'pokemon':
                # o TCG Live registra algumas Habilidades como "jogou <Pokémon>." (ex.: Run Away Draw)
                ab = self._find(opts, lambda o: o.kind == 'ability' and o.value[0].name == f['cardName'])
                if ab is not None:
                    return ab
        if k in ('blog_loc_played_card', 'blog_loc_played_to_stadium', 'blog_loc_played_to_fallback'):
            nm = f['cardName']
            self._ensure_and_refresh(g, p, nm)
            return self._find(g.prompt.options, lambda o: o.kind in ('trainer', 'tool') and o.card.name == nm)
        if k.startswith('blog_loc_evolved'):
            src, dst, where = f['sourcePokemonCardName'], f['targetPokemonCardName'], self._where(k)
            self._ensure_and_refresh(g, p, dst)
            return self._find(g.prompt.options, lambda o: o.kind == 'evolve' and o.card.name == dst and
                              self._slot_matches(g, o.value[1], src, where))
        if k.startswith('blog_loc_attach_card'):
            src, dst, where = f['sourceCardName'], f['targetCardName'], self._where(k)
            self._ensure_and_refresh(g, p, src)
            return self._find(g.prompt.options, lambda o: o.kind in ('attach', 'tool') and o.card.name == src and
                              self._slot_matches(g, o.value[1], dst, where))
        if k == 'blog_loc_used_attack' or k in ATTACK_KEYS:
            mon, name = f.get('attackingPokemonCardName'), f['attackName']
            ab = self._find(opts, lambda o: o.kind == 'ability' and o.value[1].name == name and o.value[0].name == mon)
            if ab is not None:
                return ab
            at = self._find(opts, lambda o: o.kind == 'attack' and o.value.name == name)
            if at is not None:
                return at
            # segundo ataque (Festival Lead): o log mostra "usou Festival Lead" e o ataque escolhido
            if any(o.label.startswith('Atacar de novo') for o in opts):
                chosen = next((x.f.get('selectedOption') for x in e.subs if x.key == 'blog_loc_selected_option'), None)
                chosen = chosen or next((x.f.get('attackName') for x in e.subs if x.key in ATTACK_KEYS), None)
                i2 = self._find(opts, lambda o: o.kind == 'attack' and o.value.name == chosen)
                if i2 is not None:
                    return i2
            # versão errada de algum Pokémon em jogo? tenta outras versões até a jogada ficar disponível
            fixed = self._repair_versions(g, p, lambda: self._find(
                g.prompt.options, lambda o: (o.kind == 'ability' and o.value[1].name == name) or
                (o.kind == 'attack' and o.value.name == name)))
            if fixed is not None:
                return fixed
            # versão errada da carta? troca pela versão que tem este ataque/habilidade
            for s_ in pl.in_play():
                if s_.name == mon and not any(a.name == name for a in s_.d.attacks + s_.d.abilities):
                    alt = [d for d in self.D.named(mon) if any(a.name == name for a in d.attacks + d.abilities)]
                    if alt:
                        s_.cards[-1].d = alt[0]
                        self.report.notes.append(f'versão de {mon} corrigida para {alt[0].id}')
                        g.refresh()
                        return self.map_main(g, p, e, turn_events, idx)
            return None
        if k == 'blog_loc_retreated':
            nxt = next((x for x in turn_events[idx + 1:] if x.key == 'blog_loc_promote_to_active'), None)
            if nxt is None:
                return self._find(opts, lambda o: o.kind == 'retreat')
            nm = nxt.f['cardName']
            return self._find(opts, lambda o: o.kind == 'retreat' and o.value.name == nm)
        return None

    def _repair_versions(self, g, p, probe):
        """Troca versões de cartas em jogo (mesmo nome) até `probe()` encontrar a opção desejada."""
        for q in (p, 1 - p):
            for s_ in g.players[q].in_play():
                for c in s_.cards:
                    alts = [d for d in self.D.named(c.d.name) if d is not c.d]
                    if not alts:
                        continue
                    orig = c.d
                    for d in alts:
                        c.d = d
                        g.refresh()
                        i = probe()
                        if i is not None:
                            self.report.notes.append(f'versão de {d.name} ajustada para {d.id}')
                            return i
                    c.d = orig
                    g.refresh()
        return None

    def _ensure_and_refresh(self, g, p, name):
        pl = g.players[p]
        if any(c.d.name == name for c in pl.hand):
            return
        self.ensure_in(g, p, 'hand', name)
        g.refresh()

    def _find(self, opts, pred):
        hits = []
        for i, o in enumerate(opts):
            try:
                if pred(o):
                    hits.append(i)
            except Exception:
                continue
        if not hits:
            return None
        if len(hits) == 1:
            return hits[0]
        # várias opções equivalentes no log (ex.: dois Applin no Banco): ponto de retrocesso.
        # Preferência: o Pokémon mais "desenvolvido" (mais Energia/Ferramentas, entrou antes).
        def weight(i):
            o = opts[i]
            v = o.value
            slot = v[1] if isinstance(v, tuple) and len(v) == 2 and hasattr(v[1], 'energy') else \
                (v if hasattr(v, 'energy') else None)
            if slot is None:
                return (0, 0, 0)
            return (-len(slot.energy), -len(slot.tools), slot.turn_entered)
        hits.sort(key=weight)
        labels = [opts[i].label for i in hits]
        if len(set(labels)) == 1 and all(opts[i].kind in ('card', 'done') for i in hits):
            return hits[0]
        k = self.amb_counter
        self.amb_counter += 1
        alt = self.forced.get(k, 0)
        self.amb_points.append((k, len(hits)))
        return hits[min(alt, len(hits) - 1)]

    # ------------------------------------------------------------------ respostas a escolhas
    def answer(self, g, pr):
        opts = pr.options
        h = pr.hint
        if h in ('yes_no',):
            # habilidade opcional ("Usar X?"): sim se o próximo evento principal é o uso dela
            m = re.search(r'Usar a Habilidade (.+)\?', pr.text)
            if m:
                nxt = self._peek_main(g)
                if nxt is not None and nxt.key == 'blog_loc_used_attack' and nxt.f['attackName'] == m.group(1):
                    self._consume_main(g, nxt)
                    return self._find(opts, lambda o: o.kind == 'yes')
                return self._find(opts, lambda o: o.kind == 'no')
            return self._find(opts, lambda o: o.kind == ('yes' if self._evidence_yes(pr.text) else 'no'))
        if h in ('promote', 'switch', 'gust', 'target', 'opp_target', 'counters', 'attach_target', 'evolve_target',
                 'bench_target', 'damage_target', 'heal_target', 'move_from'):
            names = Counter(self._slot_names_from_ctx(h, pr.player))
            kos = {x.f.get('cardName') for x in self.ctx_events if x.key == 'blog_loc_knockout'}
            multi = h in ('damage_target', 'bench_target', 'counters', 'target', 'opp_target')
            order = list(dict.fromkeys(self._slot_names_from_ctx(h, pr.player)))
            for nm in order:
                if multi and self.slot_used[nm] >= names[nm]:
                    continue
                hits = [j for j, o in enumerate(opts) if o.value is not None and getattr(o.value, 'name', None) == nm]
                if not hits:
                    continue
                if multi and nm in kos and len(hits) > 1:
                    # o log diz que este Pokémon foi nocauteado: o mais danificado dos homônimos
                    i = max(hits, key=lambda j: getattr(opts[j].value, 'damage', 0))
                else:
                    i = self._find(opts, lambda o: o.value is not None and getattr(o.value, 'name', None) == nm)
                if multi:
                    self.slot_used[nm] += 1
                return i
            return 0
        if h in ('discard_energy', 'retreat_energy', 'discard_energy_any', 'pick_energy') and \
                any(o.kind == 'card' for o in opts):
            # o log diz quais Energias saíram do Pokémon ("X was discarded from Y")
            named = Counter()
            for x in self.ctx_events:
                if x.key == 'blog_loc_knockout':
                    break
                if x.key in ('blog_loc_discarded_attachment', 'blog_loc_discarded_attachment_multi'):
                    named.update(self._list(x))
            for nm in (named - self.disc_used):
                i = self._find(opts, lambda o: o.kind == 'card' and o.value.name == nm)
                if i is not None:
                    self.disc_used[nm] += 1
                    return i
        sel = [x.f.get('selectedOption') for x in self.ctx_events if x.key == 'blog_loc_selected_option']
        for v in sel:
            i = self._find(opts, lambda o: o.label == v or getattr(o.value, 'name', None) == v)
            if i is not None:
                return i
        if any(o.kind == 'card' for o in opts):
            for nm in list(self.want):
                i = self._find(opts, lambda o: o.kind == 'card' and o.value.name == nm)
                if i is not None:
                    self.want.remove(nm)
                    return i
            done = self._find(opts, lambda o: o.kind == 'done')
            return done if done is not None else 0
        return 0

    def _evidence_yes(self, text):
        """Decide escolhas opcionais (sim/não) pelos sub-eventos que o log registrou para a ação."""
        evs = []
        for x in self.ctx_events:      # o que vem depois do nocaute (prêmios etc.) não é efeito do ataque
            if x.key == 'blog_loc_knockout':
                break
            evs.append(x)
        keys = {x.key for x in evs}
        t = text.lower()
        if 'energia' in t and ('dano' in t or 'descartar' in t or 'devolver' in t):
            return bool(keys & {'blog_loc_discarded_attachment', 'blog_loc_discarded_attachment_multi',
                                'blog_loc_move_to_hand', 'blog_loc_shuffled_card_into_deck', 'blog_loc_move_to_deck'})
        if 'estádio' in t or 'estadio' in t:
            return 'blog_loc_discarded_from_board' in keys or 'blog_loc_move_to_discard' in keys
        if 'trocar' in t:
            return bool(keys & {'blog_loc_switched_active', 'blog_loc_promote_to_active'})
        if 'embaralhar' in t:
            return bool(keys & {'blog_loc_move_to_deck', 'blog_loc_shuffled_card_into_deck'})
        if 'buscar' in t:
            return bool(keys & {'blog_loc_drew_card', 'blog_loc_drew_then_play_bench',
                                'blog_loc_drew_then_play_bench_multi'})
        return True

    def _slot_names_from_ctx(self, hint, chooser):
        out = []
        for e in self.ctx_events + list(self._lookahead):
            f = e.f
            if e.key == 'blog_loc_promote_to_active' and hint in ('promote', 'switch', 'gust'):
                out.append(f['cardName'])
            elif e.key == 'blog_loc_switched_active':
                out.append(f['targetCardName'])
            elif e.key.startswith('blog_loc_attach_card') and hint == 'attach_target':
                out.append(f['targetCardName'])
            elif e.key in ATTACK_KEYS and hint in ('damage_target', 'bench_target'):
                out.append(f.get('targetPokemonCardName'))
            elif e.key in ('blog_loc_player_placed_dc', 'blog_loc_player_placed_single_dc', 'blog_loc_secondary_damage',
                           'blog_loc_secondary_weak_attack', 'blog_loc_secondary_resistance_attack') and \
                    hint not in ('promote', 'switch', 'gust'):
                out.append(f.get('targetPokemonCardName'))
            elif e.key in ('blog_loc_player_moved_dc', 'blog_loc_player_moved_single_dc'):
                out.append(f['sourcePokemonCardName'] if hint == 'move_from' else f['targetPokemonCardName'])
            elif e.key.startswith('blog_loc_evolved'):
                out.append(f['sourcePokemonCardName'])
        return [x for x in out if x]

    _lookahead = ()

    def _peek_main(self, g):
        t = self._turn_idx(g)
        if t is None:
            return None
        evs = self.turn_events[t].events
        i = self.cursor.get(t, 0)
        while i < len(evs) and not self._actionable(evs[i]):
            i += 1
        return evs[i] if i < len(evs) else None

    def _consume_main(self, g, e):
        t = self._turn_idx(g)
        evs = self.turn_events[t].events
        i = evs.index(e)
        self.cursor[t] = i + 1
        self.report.actions_done += 1
        self.ctx_events += [e] + list(e.subs)
        for s in e.subs:
            if s.key == 'blog_loc_drew_card':
                self.want += self._list(s)
        self.prepare_extra(g, e)

    def prepare_extra(self, g, e):
        p = g.prompt.player if g.prompt is not None else g.current
        for s in e.subs:
            names = self._list(s)
            if s.key == 'blog_loc_drew_card':
                for nm in names:
                    self.ensure_in(g, p, 'deck', nm)
            elif s.key.startswith('blog_loc_attach_card'):
                self.ensure_in(g, p, 'deck', s.f['sourceCardName'], top=True)
                self.want.append(s.f['sourceCardName'])

    def _turn_idx(self, g):
        t = g.turn - 1
        return t if 0 <= t < len(self.turn_events) else None

    # ------------------------------------------------------------------ setup
    def setup_info(self):
        info = {'first': None, 'active': {}, 'bench': {0: [], 1: []}, 'hand': {}, 'mulligans': {0: 0, 1: 0}}
        if not self.setup:
            return info
        for e in self.setup.events:
            k, f = e.key, e.f
            if k == 'blog_loc_going_first':
                info['first'] = self.pidx(f['playerName'])
            elif k == 'blog_loc_going_second':
                q = self.pidx(f['playerName'])
                info['first'] = None if q is None else 1 - q
            elif k in ('blog_loc_play_to_active', 'blog_loc_played_to_active'):
                info['active'][self.pidx(f['playerName'])] = f['cardName']
            elif k in ('blog_loc_play_to_bench', 'blog_loc_played_to_bench'):
                info['bench'][self.pidx(f['playerName'])].append(f['cardName'])
            elif k == 'blog_loc_draw_opening_hand':
                q = self.pidx(f['playerName'])
                lst = [c for s in e.subs for c in s.cards]
                info['hand'][q] = lst
            elif k in ('blog_loc_took_mulligan_single', 'blog_loc_took_mulligan_multi', 'blog_loc_took_mulligans'):
                q = self.pidx(f['playerName'])
                info['mulligans'][q] = int(f.get('numMulligans', 1))
        return info

    # ------------------------------------------------------------------ execução
    def run(self):
        S = self.setup_info()
        first = S['first'] if S['first'] is not None else 0
        # 60 cartas ocultas por jogador; a mão inicial é preparada pelo oráculo de compras
        decks = [[UNKNOWN_ID] * 60, [UNKNOWN_ID] * 60]
        for q in (0, 1):
            hand = list(S['hand'].get(q) or [])
            need = [S['active'].get(q)] + S['bench'][q]
            for nm in need:
                if nm and nm not in hand:
                    hand.append(nm)
            hand = hand[:7] + [None] * (7 - len(hand[:7]))
            self.pending_draws[q] = [None] * (7 * S['mulligans'][q]) + hand
        try:
            g = ReplayGame(self, decks[0], decks[1], seed=12345, names=tuple(self.names), first_player=first)
        except Desync as ex:
            self.report.divergence = f'preparação: {ex}'
            return self.report
        self.report.game = g
        self.g = g
        try:
            self._loop(g, S)
        except Desync as ex:
            self.report.divergence = str(ex)
        self.report.turns_done = min(g.turn, self.report.turns_total)
        return self.report

    def _loop(self, g, S):
        steps = 0
        while not g.done:
            steps += 1
            if steps > 20000:
                raise Desync('limite de passos')
            pr = g.prompt
            if pr.hint == 'setup_active':
                nm = S['active'].get(pr.player)
                i = self._find(pr.options, lambda o: o.value.name == nm)
                if i is None:
                    raise Desync(f'Ativo inicial {nm} não disponível: {[o.label for o in pr.options]}')
                self._step(g, i)
                continue
            if pr.hint == 'setup_bench':
                want = list(S['bench'][pr.player])
                placed = pr.data.get('picked', [])
                for c in placed:
                    if c.name in want:
                        want.remove(c.name)
                i = self._find(pr.options, lambda o: o.kind == 'card' and o.value.name in want)
                self._step(g, i if i is not None else self._find(pr.options, lambda o: o.kind == 'done'))
                continue
            if pr.hint == 'main':
                t = self._turn_idx(g)
                if t is None:
                    self.report.finished = True
                    return
                evs = self.turn_events[t].events
                i = self.cursor.get(t, 0)
                while i < len(evs) and not self._actionable(evs[i]):
                    i += 1
                if i >= len(evs):
                    # log acabou neste turno (desistência ou fim): encerra
                    if t == len(self.turn_events) - 1:
                        self.report.finished = True
                        return
                    raise Desync(f'turno {g.turn}: o log não tem mais ações, mas o motor esperava uma')
                e = evs[i]
                p = pr.player
                self.cursor[t] = i + 1
                self._lookahead = evs[i + 1:i + 6]
                conseq = []
                j = i + 1
                while j < len(evs) and not self._actionable(evs[j]):
                    conseq.append(evs[j])
                    conseq += evs[j].subs
                    j += 1
                self.prepare(g, p, e, conseq)
                g.refresh()
                self.collect_prizes(evs, i + 1)
                choice = self.map_main(g, p, e, evs, i)
                if choice is None:
                    raise Desync(f'turno {g.turn} ({g.players[p].name}): não achei a jogada "{e.line}" entre '
                                 f'{[o.label for o in g.prompt.options]}')
                if e.key not in ('blog_loc_manual_end',):
                    self.report.actions_done += 1
                else:
                    self.report.actions_done += 1
                before_log = len(g.log)
                before_ko = len(g.ko_log)
                self._step(g, choice)
                self._resolve_pending(g)
                if e.key in ATTACK_KEYS:
                    self._check_damage(g, e, before_log, p)
                if self.frames is not None:
                    from ..view import game_view
                    self.frames.append({'label': e.line, 'turn': g.turn, 'player': self.names[p],
                                        'state': game_view(g, 'all')})
                self._check_kos(g, conseq, before_ko, e)
                continue
            self._step(g, self.answer(g, pr))
        self.report.finished = True

    def _resolve_pending(self, g):
        """Responde escolhas que surgiram dentro da ação (buscas, alvos...) antes de checar consequências."""
        guard = 0
        while not g.done and g.prompt is not None and g.prompt.hint != 'main' and guard < 200:
            guard += 1
            self._step(g, self.answer(g, g.prompt))

    def _check_kos(self, g, conseq, before_ko, e):
        from collections import Counter
        want = Counter(x.f['cardName'] for x in conseq if x.key == 'blog_loc_knockout')
        got = Counter(k['name'] for k in g.ko_log[before_ko:])
        if want != got and not g.done:
            raise Desync(f'turno {g.turn}: nocautes diferentes após "{e.line[:80]}" — log {dict(want)}, motor {dict(got)}')

    def _step(self, g, i):
        if self.record and g.prompt is not None and len(g.prompt.options) > 1:
            from ..encode import encode
            self.report.samples.append((encode(g), i, g.prompt.player))
        g.step(i)

    def _check_damage(self, g, e, start, attacker):
        want = int(e.f['numDamage'])
        target = e.f['targetPokemonCardName']
        got = 0
        for x in g.log[start:]:
            m = re.match(r'^.+ causou (\d+) de dano em (.+) \((Ativo|Banco \d+)\)$', x['msg'])
            if m and m.group(2) == target and m.group(3) == 'Ativo':
                got = int(m.group(1))
                break
        self.report.damage_checks.append((g.turn, e.line, want, got))
        if want != got and not g.done:
            # o log oficial é a referência: sincroniza o dano para seguir a partida (sem mudar nocautes)
            opp = g.players[1 - attacker].active
            if opp is not None and opp.name == target:
                new = opp.damage + (want - got)
                if 0 <= new < g.hp(opp):
                    opp.damage = new
                    self.report.notes.append(f'turno {g.turn}: dano em {target} ajustado ao log ({got} → {want})')


def replay_log(text, record=False, max_attempts=1000, max_seconds=90) -> ReplayReport:
    """Reproduz o log; em caso de divergência, tenta alternativas nos pontos ambíguos (retrocesso).

    O log não diz, por exemplo, em qual de dois Slowpoke do Banco uma Energia foi ligada; a escolha
    errada só aparece turnos depois. A busca em profundidade testa as alternativas até a partida
    inteira bater com o log (limitada por número de tentativas e tempo)."""
    import time
    t0 = time.time()
    log = parse_log(text)
    if len(log.players) < 2:
        r = ReplayReport(players=log.players)
        r.divergence = 'não encontrei os dois jogadores no log'
        return r
    forced = {}
    best = None
    for attempt in range(max_attempts):
        rp = Replayer(log, record=record)
        rp.forced = dict(forced)
        rep = rp.run()
        rep.forced = dict(rp.forced)
        rep.notes.append(f'tentativas: {attempt + 1}')
        if best is None or rep.actions_done > best.actions_done or rep.finished:
            best = rep
        if rep.finished and not rep.divergence:
            return rep
        if time.time() - t0 > max_seconds:
            break
        # próxima alternativa: último ponto ambíguo que ainda tem opções
        pts = rp.amb_points
        while pts:
            k, n = pts.pop()
            cur = forced.get(k, 0)
            if cur + 1 < n:
                forced = {kk: v for kk, v in forced.items() if kk < k}
                forced[k] = cur + 1
                break
        else:
            break
    return best
