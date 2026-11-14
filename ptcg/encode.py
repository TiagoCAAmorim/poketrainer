"""Codificação do estado e das opções em arrays numpy (só informação visível ao jogador).

Observação (perspectiva do jogador `p`):
  slot_ids   int[18]      carta do topo de cada posição (9 minhas: ativo+8 banco, 9 do oponente)
  slot_tool  int[18]      ferramenta ligada
  slot_feats f32[18, SLOT_F]
  hand_ids   int[MAX_HAND] minha mão (0 = vazio)
  discard    f32[2, V]    contagem de cartas no descarte (meu, oponente)
  glob       f32[GLOB_F]  escalares (tamanhos de zonas, prêmios, flags do turno, tipo de decisão)
  ctx_ids    int[2]       estádio em jogo, carta que originou a decisão
Versão 2 (`encode(g, versao=2)`; a versão 1 continua sendo o padrão e as redes antigas a usam) acrescenta:
  deck_ids/deck_cnt  int/f32[BAG]   cartas que ainda estão no MEU deck+prêmios (o jogador conhece a própria lista)
  disc_ids/disc_cnt  int/f32[2*BAG] descarte (meu, oponente) como lista de cartas distintas + contagem
  slot_x     f32[18, SLOT_X]        por ataque (até 3): pode pagar, dano estimado no ativo oposto, nocauteia
  glob2      f32[GLOB2_F]           Zona Perdida, prêmios que faltam, ameaças de nocaute dos dois lados
Opções:
  opt_ids    int[A]       carta envolvida na opção
  opt_tids   int[A]       carta do Pokémon alvo (se houver)
  opt_feats  f32[A, OPT_F]
"""
from __future__ import annotations

import numpy as np

from .carddb import vocab_size
from .core import CONDITIONS, ENERGY_TYPES

MAX_HAND = 40
MAX_BENCH = 8                 # Area Zero Underdepths permite até 8
PER_SIDE = 1 + MAX_BENCH
N_SLOTS = 2 * PER_SIDE
V = vocab_size()
HINTS = ['main', 'first', 'setup_active', 'setup_bench', 'promote', 'switch', 'search', 'search_bench',
         'search_energy', 'discard', 'pick', 'pick_energy', 'recover', 'attach_target', 'gust', 'counters',
         'yes_no', 'discard_energy_any', 'retreat_energy', 'look', 'candy', 'evolve_target', 'attach_from_hand',
         'order', 'move_energy', 'discard_energy', 'copy_attack', 'mode', 'heal_target', 'move_from', 'amount',
         'target', 'opp_target', 'bench_target', 'damage_target', 'discard_bench', 'bottom', 'other']
OPTION_KINDS = ['end', 'play_basic', 'evolve', 'attach', 'tool', 'trainer', 'ability', 'stadium', 'retreat',
                'attack', 'card', 'slot', 'opp_slot', 'yes', 'no', 'done', 'text']
SLOT_F = 12 + len(ENERGY_TYPES) + len(CONDITIONS) + 3
GLOB_F = 22 + len(HINTS)
OPT_F = len(OPTION_KINDS) + 3 + 7 + 3 + 2
VERSOES = (1, 2)
BAG = 60                      # cartas distintas por zona (um deck de 60 tem no máximo 60)
MAX_ATK = 3
SLOT_X = 3 * MAX_ATK + 2
GLOB2_F = 8


def _slot_feats(g, s, is_active, p_owner):
    f = np.zeros(SLOT_F, np.float32)
    if s is None:
        return f
    hp = g.hp(s)
    f[0] = 1.0
    f[1] = float(is_active)
    f[2] = hp / 340
    f[3] = (hp - s.damage) / 340
    f[4] = s.damage / 340
    f[5 + min(s.d.stage, 2)] = 1.0
    f[8] = s.d.base_prizes / 3
    f[9] = g.retreat_cost(s) / 4
    hand = g.players[p_owner].hand
    f[10] = float(any(c.d.kind == 'pokemon' and g.can_evolve(p_owner, s, c) for c in hand))
    f[11] = float(s.turn_entered == g.turn)
    o = 12
    for _, units in g.energy_units(s):
        for u in units:
            for t in u:
                if t in ENERGY_TYPES:
                    f[o + ENERGY_TYPES.index(t)] += 0.25 / max(1, len(u))
    o += len(ENERGY_TYPES)
    for i, c in enumerate(CONDITIONS):
        f[o + i] = float(c in s.conditions)
    o += len(CONDITIONS)
    f[o] = len(s.energy) / 6
    f[o + 1] = float(g.can_pay(s, g.attack_cost(s, s.d.attacks[-1]))) if s.d.attacks else 0.0
    f[o + 2] = float(any(ab.impl is not None and ab.impl.kind == 'activated' and g.can_use_ability(p_owner, s, ab) for ab in s.d.abilities))
    return f


def encode_state(g, p):
    me, op = g.players[p], g.players[1 - p]
    slot_ids = np.zeros(N_SLOTS, np.int64)
    slot_tool = np.zeros(N_SLOTS, np.int64)
    slot_feats = np.zeros((N_SLOTS, SLOT_F), np.float32)
    hide_opp = not g.setup_done
    for side, pl in enumerate((me, op)):
        if side == 1 and hide_opp:
            continue
        slots = ([pl.active] + list(pl.bench) + [None] * MAX_BENCH)[:PER_SIDE]
        for j, s in enumerate(slots):
            k = side * PER_SIDE + j
            if s is None:
                continue
            slot_ids[k] = s.d.idx
            slot_tool[k] = s.tools[0].d.idx if s.tools else 0
            slot_feats[k] = _slot_feats(g, s, j == 0, pl.idx)
    hand_ids = np.zeros(MAX_HAND, np.int64)
    for i, c in enumerate(me.hand[:MAX_HAND]):
        hand_ids[i] = c.d.idx
    discard = np.zeros((2, V), np.float32)
    for side, pl in enumerate((me, op)):
        for c in pl.discard:
            discard[side, c.d.idx] += 0.25
    pr = g.prompt
    glob = np.zeros(GLOB_F, np.float32)
    glob[0] = len(me.deck) / 60
    glob[1] = len(op.deck) / 60
    glob[2] = len(me.hand) / 20
    glob[3] = len(op.hand) / 20
    glob[4] = len(me.prizes) / 6
    glob[5] = len(op.prizes) / 6
    glob[6] = g.turn / 40
    glob[7] = float(me.energy_attached)
    glob[8] = float(me.supporter_played)
    glob[9] = float(me.retreated)
    glob[10] = float(me.stadium_played)
    glob[11] = float(me.stadium_used)
    glob[12] = float(g.first_player == p)
    glob[13] = float(g.turn <= 2)
    glob[14] = float(g.stadium is not None and g.stadium.owner == p)
    glob[15] = float(g.stadium is not None and g.stadium.owner != p)
    glob[16] = len(me.bench) / 5
    glob[17] = len(op.bench) / 5
    glob[18] = float(g.current == p)
    glob[19] = float(g.setup_done)
    glob[20] = (pr.data.get('chosen', 0) / 6) if pr else 0.0
    glob[21] = (pr.data.get('max', 0) / 6) if pr else 0.0
    hint = pr.hint if pr else 'other'
    glob[22 + HINTS.index(hint if hint in HINTS else 'other')] = 1.0
    ctx_ids = np.zeros(2, np.int64)
    ctx_ids[0] = g.stadium.d.idx if g.stadium else 0
    if pr is not None and pr.source is not None and hasattr(pr.source, 'd'):
        ctx_ids[1] = pr.source.d.idx
    return {'slot_ids': slot_ids, 'slot_tool': slot_tool, 'slot_feats': slot_feats, 'hand_ids': hand_ids,
            'discard': discard.reshape(-1), 'glob': glob, 'ctx_ids': ctx_ids}


def encode_options(g, p, options):
    A = len(options)
    ids = np.zeros(A, np.int64)
    tids = np.zeros(A, np.int64)
    feats = np.zeros((A, OPT_F), np.float32)
    for i, o in enumerate(options):
        kind = o.kind if o.kind in OPTION_KINDS else 'text'
        feats[i, OPTION_KINDS.index(kind)] = 1.0
        b = len(OPTION_KINDS)
        if o.card is not None and hasattr(o.card, 'd'):
            ids[i] = o.card.d.idx
        if o.target is not None:
            owner, pos = o.target
            feats[i, b + (1 if owner == p else 2)] = 1.0
            feats[i, b + 3 + min(pos, 5) + 1] = 1.0   # posições 5+ compartilham o último índice
            s = g.players[owner].active if pos == 0 else (
                g.players[owner].bench[pos - 1] if pos - 1 < len(g.players[owner].bench) else None)
            if s is not None:
                tids[i] = s.d.idx
                feats[i, b + 3 + 7 + 3] = (g.hp(s) - s.damage) / 340
        else:
            feats[i, b] = 1.0
            feats[i, b + 3] = 1.0
        if o.attack >= 0:
            feats[i, b + 3 + 7 + 1 + min(o.attack, 1)] = 1.0
        else:
            feats[i, b + 3 + 7] = 1.0
        if kind == 'attack':
            me = g.players[p]
            try:
                dmg = g.estimate_attack(me.active, o.value, g.players[1 - p].active)
            except Exception:
                dmg = 0
            feats[i, b + 3 + 7 + 3 + 1] = dmg / 340
    return {'opt_ids': ids, 'opt_tids': tids, 'opt_feats': feats}


def _bag(cards, n=BAG):
    ids = np.zeros(n, np.int64)
    cnt = np.zeros(n, np.float32)
    tally = {}
    for c in cards:
        tally[c.d.idx] = tally.get(c.d.idx, 0) + 1
    for i, (k, v) in enumerate(sorted(tally.items())[:n]):
        ids[i], cnt[i] = k, v / 4
    return ids, cnt


def _attack_feats(g, s, target):
    """Por ataque: pode pagar, dano estimado em `target` (/340), nocauteia; + maior dano pagável, algum nocauteia."""
    f = np.zeros(SLOT_X, np.float32)
    left = g.hp_left(target) if target is not None else None
    best, ko_any = 0, 0.0
    for i, atk in enumerate(s.d.attacks[:MAX_ATK]):
        try:
            pay = g.can_pay(s, g.attack_cost(s, atk))
            dmg = g.estimate_attack(s, atk, target) if target is not None else atk.damage
        except Exception:
            pay, dmg = False, 0
        dmg = max(0, int(dmg or 0))
        ko = float(pay and left is not None and dmg >= left > 0)
        f[3 * i], f[3 * i + 1], f[3 * i + 2] = float(pay), dmg / 340, ko
        if pay:
            best = max(best, dmg)
            ko_any = max(ko_any, ko)
    f[3 * MAX_ATK], f[3 * MAX_ATK + 1] = best / 340, ko_any
    return f


def encode_v2_extra(g, p):
    me, op = g.players[p], g.players[1 - p]
    deck_ids, deck_cnt = _bag(list(me.deck) + list(me.prizes))
    d0, c0 = _bag(me.discard)
    d1, c1 = _bag(op.discard)
    slot_x = np.zeros((N_SLOTS, SLOT_X), np.float32)
    if g.setup_done:
        for side, (pl, other) in enumerate(((me, op), (op, me))):
            slots = ([pl.active] + list(pl.bench))[:PER_SIDE]
            for j, s in enumerate(slots):
                if s is not None:
                    slot_x[side * PER_SIDE + j] = _attack_feats(g, s, other.active)
    glob2 = np.zeros(GLOB2_F, np.float32)
    glob2[0] = len(me.lost_zone) / 10
    glob2[1] = len(op.lost_zone) / 10
    glob2[2] = float(len(me.prizes) <= 2)
    glob2[3] = float(len(op.prizes) <= 2)
    glob2[4] = slot_x[0, 3 * MAX_ATK + 1]                          # meu ativo nocauteia o ativo dele agora
    glob2[5] = slot_x[PER_SIDE, 3 * MAX_ATK + 1]                   # o ativo dele nocauteia o meu (com o que tem)
    glob2[6] = float(slot_x[1:PER_SIDE, 3 * MAX_ATK + 1].max(initial=0))   # algum do meu banco nocautearia
    glob2[7] = float(op.active is not None and op.active.d.base_prizes >= 2)
    return {'deck_ids': deck_ids, 'deck_cnt': deck_cnt, 'disc_ids': np.concatenate([d0, d1]),
            'disc_cnt': np.concatenate([c0, c1]), 'slot_x': slot_x, 'glob2': glob2}


def encode(g, p=None, versao=1):
    p = g.prompt.player if p is None else p
    obs = encode_state(g, p)
    if versao >= 2:
        obs.update(encode_v2_extra(g, p))
    obs.update(encode_options(g, p, g.prompt.options))
    return obs
