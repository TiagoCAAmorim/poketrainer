"""Estruturas de dados do simulador (motor v2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Tipos: G Grama, R Fogo, W Água, L Elétrico, P Psíquico, F Lutador, D Escuridão, M Metal,
#        N Dragão, C Incolor, Y Fada (não existe mais, mantido por compatibilidade)
TYPES = ['G', 'R', 'W', 'L', 'P', 'F', 'D', 'M', 'N', 'C', 'Y']
ENERGY_TYPES = ['G', 'R', 'W', 'L', 'P', 'F', 'D', 'M']
ANY = frozenset(ENERGY_TYPES)             # unidade de energia "de todos os tipos"
COLORLESS = frozenset({'C'})              # unidade que só paga custo Incolor
TYPE_NAMES = {'G': 'Grass', 'R': 'Fire', 'W': 'Water', 'L': 'Lightning', 'P': 'Psychic', 'F': 'Fighting',
              'D': 'Darkness', 'M': 'Metal', 'N': 'Dragon', 'C': 'Colorless', 'Y': 'Fairy'}
NAME_TO_TYPE = {v: k for k, v in TYPE_NAMES.items()}
CONDITIONS = ['asleep', 'paralyzed', 'confused', 'poisoned', 'burned']
EXCLUSIVE_CONDITIONS = {'asleep', 'paralyzed', 'confused'}
COND_NAMES = {'Asleep': 'asleep', 'Paralyzed': 'paralyzed', 'Confused': 'confused', 'Poisoned': 'poisoned',
              'Burned': 'burned'}
DEFAULT_BENCH = 5


class GameOver(Exception):
    def __init__(self, winner: int, reason: str):
        super().__init__(reason)
        self.winner = winner
        self.reason = reason


class NotImplementedEffect(Exception):
    pass


# ------------------------------------------------------------------ implementações de efeitos
@dataclass
class AttackImpl:
    """Implementação de um ataque.
    run(g, ctx): generator executado no lugar do ataque padrão. Deve chamar
      `yield from g.main_damage(ctx)` no ponto em que o dano principal é causado
      (ou deixar `auto_damage=True` para o motor causar o dano depois de `pre` e antes de `post`).
    """
    pre: Optional[Callable] = None        # f(g, ctx) antes do dano (pode alterar ctx.damage)
    post: Optional[Callable] = None       # f(g, ctx) depois do dano
    run: Optional[Callable] = None        # controle total (ignora pre/post/auto)
    can_use: Optional[Callable] = None    # f(g, slot) -> bool
    estimate: Optional[Callable] = None   # f(g, slot, target) -> dano estimado
    ignore_effects: bool = False          # "isn't affected by any effects on your opponent's Active Pokémon"
    ignore_weakness: bool = False
    ignore_resistance: bool = False
    status: str = 'ok'                    # 'ok' | 'partial' | 'missing'
    note: str = ''


@dataclass
class AbilityImpl:
    kind: str = 'activated'   # activated | passive | on_bench (ao ir pro banco da mão) | on_evolve | trigger
    can_use: Optional[Callable] = None    # f(g, p, slot) -> bool
    run: Optional[Callable] = None        # f(g, p, slot)
    hooks: dict = field(default_factory=dict)    # consultas estáticas (ver Game.fold/allowed)
    events: dict = field(default_factory=dict)   # gatilhos: nome -> f(g, src, **ctx)
    once_per_turn: bool = True
    shared_key: Optional[str] = None
    optional: bool = True
    self_ko: bool = False     # habilidades que nocauteiam o próprio Pokémon (para Damp)
    status: str = 'ok'
    note: str = ''


@dataclass
class TrainerImpl:
    run: Optional[Callable] = None         # f(g, p, card)
    can_play: Optional[Callable] = None    # f(g, p, card) -> bool
    hooks: dict = field(default_factory=dict)   # ferramentas / estádios / energias especiais
    events: dict = field(default_factory=dict)
    action: Optional[Callable] = None      # estádio: f(g, p) ação "uma vez por turno"
    action_can: Optional[Callable] = None  # estádio: f(g, p) -> bool
    units: Optional[Callable] = None       # energia: f(g, card, slot) -> [frozenset,...]
    can_attach: Optional[Callable] = None  # energia/ferramenta: f(g, p, card, slot) -> bool
    on_attach: Optional[Callable] = None   # energia: f(g, p, card, slot, from_hand) gatilho
    attacks: list = field(default_factory=list)  # ferramentas que concedem ataques (TM)
    first_turn_ok: bool = False            # Apoiador permitido no 1º turno de quem começa
    status: str = 'ok'
    note: str = ''


# ------------------------------------------------------------------ definições de carta
@dataclass(eq=False)
class AttackDef:
    name: str
    cost: list
    damage: int = 0
    suffix: str = ''          # '+', '×', '-' ou ''
    text: str = ''
    impl: Optional[AttackImpl] = None
    owner_name: str = ''      # carta de origem (para ataques concedidos por ferramentas)

    @property
    def damage_label(self):
        return f'{self.damage}{self.suffix}' if self.damage or self.suffix else ''


@dataclass(eq=False)
class AbilityDef:
    name: str
    text: str
    impl: Optional[AbilityImpl] = None


@dataclass(eq=False)
class CardDef:
    id: str
    name: str
    kind: str                         # pokemon | trainer | energy
    name_pt: Optional[str] = None
    subtype: Optional[str] = None     # item | supporter | stadium | tool | basic | special
    stage: int = 0
    evolves_from: Optional[str] = None
    hp: int = 0
    types: list = field(default_factory=list)
    weakness: Optional[str] = None
    resistance: Optional[str] = None
    resistance_value: int = 30
    retreat: int = 0
    attacks: list = field(default_factory=list)
    abilities: list = field(default_factory=list)
    tags: set = field(default_factory=set)
    text: str = ''
    provides: Optional[str] = None
    prints: list = field(default_factory=list)
    impl: Optional[TrainerImpl] = None
    idx: int = 0
    as_pokemon: bool = False          # fósseis: "play as if it were a Basic Pokémon"

    # --- propriedades
    @property
    def is_pokemon(self):
        return self.kind == 'pokemon'

    @property
    def is_basic(self):
        return self.kind == 'pokemon' and self.stage == 0

    @property
    def is_evolution(self):
        return self.kind == 'pokemon' and self.stage > 0

    @property
    def is_supporter(self):
        return self.subtype == 'supporter'

    @property
    def is_item(self):
        return self.kind == 'trainer' and self.subtype == 'item'

    @property
    def is_tool(self):
        return self.subtype == 'tool'

    @property
    def is_stadium(self):
        return self.subtype == 'stadium'

    @property
    def basic_energy(self):
        return self.kind == 'energy' and self.subtype == 'basic'

    @property
    def special_energy(self):
        return self.kind == 'energy' and self.subtype == 'special'

    @property
    def is_ex(self):
        return 'ex' in self.tags

    @property
    def is_mega(self):
        return 'mega' in self.tags

    @property
    def rule_box(self):
        return self.kind == 'pokemon' and bool(self.tags & {'ex', 'mega', 'v', 'radiant'})

    @property
    def base_prizes(self):
        if self.is_mega:
            return 3
        return 2 if self.rule_box else 1

    @property
    def family(self):
        """Prefixo de treinador: "Ethan's", "Team Rocket's", "N's"…"""
        if "'s " in self.name:
            return self.name.split("'s ")[0] + "'s"
        return None

    @property
    def ace_spec(self):
        return 'ace_spec' in self.tags

    @property
    def status(self):
        """Cobertura de implementação desta carta: ok | partial | missing."""
        sts = []
        if self.kind == 'pokemon':
            sts += [a.impl.status if a.impl else ('ok' if not a.text else 'missing') for a in self.attacks]
            sts += [a.impl.status if a.impl else 'missing' for a in self.abilities]
        elif not self.basic_energy:
            sts.append(self.impl.status if self.impl else 'missing')
        if not sts or all(s == 'ok' for s in sts):
            return 'ok'
        if all(s == 'missing' for s in sts):
            return 'missing'
        return 'partial'

    def __repr__(self):
        return f'<CardDef {self.id} {self.name}>'


class Card:
    __slots__ = ('uid', 'd', 'owner', 'face_up')

    def __init__(self, uid: int, d: CardDef, owner: int):
        self.uid, self.d, self.owner = uid, d, owner
        self.face_up = False

    @property
    def name(self) -> str:
        return self.d.name

    def __repr__(self):
        return f'<{self.d.name}#{self.uid}>'


class PokemonSlot:
    """Um Pokémon em jogo: pilha de evolução, energias, ferramentas, dano e condições."""

    def __init__(self, card: Card, turn: int):
        self.cards: list[Card] = [card]
        self.energy: list[Card] = []
        self.tools: list[Card] = []
        self.damage = 0
        self.conditions: set[str] = set()
        self.turn_entered = turn
        self.turn_evolved = -1
        self.ability_turns: dict[str, int] = {}
        self.paralyzed_until = -1
        self.asleep_turn = -1
        self.flags: dict = {}       # marcadores livres usados por efeitos

    @property
    def top(self) -> Card:
        return self.cards[-1]

    @property
    def d(self) -> CardDef:
        return self.cards[-1].d

    @property
    def name(self) -> str:
        return self.cards[-1].d.name

    @property
    def sid(self) -> int:
        return self.cards[0].uid

    @property
    def owner(self) -> int:
        return self.cards[0].owner

    @property
    def tool(self):
        return self.tools[0] if self.tools else None

    @property
    def stage(self) -> int:
        return self.d.stage

    @property
    def evolved(self) -> bool:
        return len([c for c in self.cards if c.d.kind == 'pokemon']) > 1

    def all_cards(self) -> list[Card]:
        return self.cards + self.energy + self.tools

    def clear_conditions(self):
        self.conditions.clear()
        self.paralyzed_until = -1


class Player:
    def __init__(self, idx: int, deck: list[Card], name: str):
        self.idx = idx
        self.name = name
        self.deck = deck             # deck[0] = topo
        self.hand: list[Card] = []
        self.discard: list[Card] = []
        self.prizes: list[Card] = []
        self.lost_zone: list[Card] = []
        self.limbo: list[Card] = []   # cartas em resolução
        self.active: Optional[PokemonSlot] = None
        self.bench: list[PokemonSlot] = []
        self.mulligans = 0
        self.went_first = False
        self.turns_taken = 0
        self.legacy_used = False
        self.reset_turn()

    def reset_turn(self):
        self.energy_attached = 0
        self.supporter_played = False
        self.retreated = False
        self.stadium_played = False
        self.stadium_used = False
        self.ability_keys: set[str] = set()
        self.played: list[str] = []    # nomes de treinadores jogados neste turno

    def in_play(self) -> list[PokemonSlot]:
        return ([self.active] if self.active else []) + list(self.bench)

    def zones(self):
        return {'deck': self.deck, 'hand': self.hand, 'discard': self.discard, 'prizes': self.prizes,
                'lost': self.lost_zone, 'limbo': self.limbo}

    def total_cards(self, stadium=None) -> int:
        n = sum(len(z) for z in self.zones().values())
        n += sum(len(s.all_cards()) for s in self.in_play())
        if stadium is not None and stadium.owner == self.idx:
            n += 1
        return n


@dataclass
class Option:
    label: str
    value: Any = None
    kind: str = 'text'
    card: Any = None
    target: Optional[tuple] = None   # (dono, posição) 0=ativo, 1..=banco
    attack: int = -1


@dataclass
class Prompt:
    player: int
    hint: str
    text: str
    options: list
    source: Any = None
    data: dict = field(default_factory=dict)


@dataclass
class Src:
    """Fonte de um efeito estático/gatilho."""
    kind: str                       # ability | tool | energy | stadium | temp
    owner: int
    card: Any = None
    slot: Optional[PokemonSlot] = None
    effect: Any = None              # TempEffect quando kind == 'temp'


@dataclass(eq=False)
class TempEffect:
    """Efeito com duração ("during your opponent's next turn", "during this turn"...)."""
    name: str
    owner: int                       # jogador que criou o efeito
    hooks: dict = field(default_factory=dict)
    events: dict = field(default_factory=dict)
    target: Optional[PokemonSlot] = None
    expires: int = 0                 # removido ao fim do turno de número `expires`
    while_active: bool = False       # termina se o alvo sair do Ativo / evoluir
    data: dict = field(default_factory=dict)


class AttackCtx:
    def __init__(self, game, player, attacker, defender, attack):
        self.game = game
        self.player = player
        self.opp = 1 - player
        self.attacker = attacker
        self.defender = defender
        self.attack = attack
        self.damage = attack.damage
        self.done_damage = 0              # dano causado ao Ativo
        self.ignore_effects = bool(attack.impl and attack.impl.ignore_effects)
        self.ignore_weakness = bool(attack.impl and attack.impl.ignore_weakness)
        self.ignore_resistance = bool(attack.impl and attack.impl.ignore_resistance)
        self.no_damage = False            # "this attack does nothing"
        self.data: dict = {}
        self.discarded_energy: list = []
