"""Otimiza uma lista de deck contra um "gauntlet" de decks adversários.

Busca local com trocas de cartas (tira N cópias de uma carta, coloca de outra), avaliando cada
candidato por simulação com as MESMAS sementes do deck atual (números aleatórios comuns),
o que reduz bastante o ruído da comparação. Candidatos promissores são confirmados com
mais partidas antes de serem aceitos.

Exemplos:
    python optimize.py tests/05_heiremans_crustle --gauntlet tests/01_hedrick_dragapult tests/02_cassiraga_alakazam_dudunsparce --iters 60
    python optimize.py meus/meu_deck --gauntlet 01_hedrick_dragapult --pool "Maximum Belt" "Night Stretcher" --games 120
    python optimize.py meus/meu_deck --gauntlet 01_hedrick_dragapult --agent model:checkpoints/best.pt

As cartas candidatas (pool) são: as do próprio deck, as outras cartas das mesmas linhas evolutivas,
todos os treinadores legais com efeito implementado e as energias básicas dos tipos já usados.
"""
import argparse
import json
import random
import time
from collections import Counter

from ptcg.carddb import db
from ptcg.decks import deck_to_text, load_deck, validate
from ptcg.sim import run_matchup


def auto_pool(base):
    """Ids de cartas candidatas a entrar no deck."""
    D = db()
    have = {D.get(i) for i in base}
    names = {d.name for d in have}
    families = set()
    for d in have:
        if d.kind == 'pokemon':
            families |= {d.name, d.evolves_from} - {None}
    pool = set(base)
    for x in D.cards.values():
        if x.status == 'missing':
            continue
        if x.kind == 'pokemon' and (x.name in families or x.evolves_from in families):
            pool.add(x.id)
        elif x.kind == 'trainer' and x.status == 'ok':
            pool.add(x.id)
        elif x.basic_energy and x.name in names:
            pool.add(x.id)
    return sorted(pool)


def resolve_name(n):
    D = db()
    if n in D.cards:
        return n
    try:
        return D.resolve(n).id
    except KeyError:
        raise SystemExit(f'Carta não encontrada: {n}')


def label(cid):
    return db().get(cid).name


def mutate(cards, pool, rng, locked):
    c = Counter(cards)
    for _ in range(100):
        k = rng.choice([1, 1, 1, 2])
        removable = [n for n, m in c.items() if m >= k and n not in locked]
        if not removable:
            continue
        out = rng.choice(removable)
        inn = rng.choice([p for p in pool if p != out])
        new = c.copy()
        new[out] -= k
        new[inn] += k
        lst = [n for n, m in new.items() for _ in range(m) if m > 0]
        if not validate(lst):
            return lst, f'-{k} {label(out)}  +{k} {label(inn)}'
    return None, ''


def score(cards, gauntlet, games, agent, seed, workers):
    total, details = 0.0, {}
    for name, opp in gauntlet.items():
        r = run_matchup(cards, opp, games, agent, agent, seed, workers)
        details[name] = r['winrate']
        total += r['winrate']
    return total / len(gauntlet), details


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('deck')
    ap.add_argument('--gauntlet', nargs='+', required=True)
    ap.add_argument('--pool', nargs='*', default=None, help='cartas candidatas extras (padrão: automático)')
    ap.add_argument('--lock', nargs='*', default=[], help='cartas que não podem ser removidas')
    ap.add_argument('--iters', type=int, default=50)
    ap.add_argument('--games', type=int, default=100, help='partidas por confronto na triagem')
    ap.add_argument('--confirm', type=int, default=300, help='partidas por confronto na confirmação')
    ap.add_argument('--margin', type=float, default=0.01)
    ap.add_argument('--agent', default='heuristic')
    ap.add_argument('--workers', type=int, default=None)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', default='optimized_deck.txt')
    args = ap.parse_args()

    base = load_deck(args.deck)
    gauntlet = {load_deck(n).name: load_deck(n).cards for n in args.gauntlet}
    pool = auto_pool(base.cards)
    if args.pool:
        pool = sorted(set(pool) | {resolve_name(n) for n in args.pool})
    rng = random.Random(args.seed)
    cur = list(base.cards)
    seed = args.seed * 100000
    cur_s, cur_d = score(cur, gauntlet, args.games, args.agent, seed, args.workers)
    print(f'Inicial: {100 * cur_s:.1f}%  {json.dumps({k: round(v, 3) for k, v in cur_d.items()})}')
    history = [{'iter': 0, 'score': cur_s, 'change': 'inicial'}]
    t = time.time()
    for it in range(1, args.iters + 1):
        cand, change = mutate(cur, pool, rng, set({resolve_name(n) for n in args.lock}))
        if cand is None:
            continue
        s, d = score(cand, gauntlet, args.games, args.agent, seed, args.workers)
        msg = f'[{it:3d}] {change:<45} {100 * s:5.1f}% (atual {100 * cur_s:.1f}%)'
        if s > cur_s + args.margin:
            cseed = seed + 7_000_000 + it * 1000      # confirmação com sementes novas
            s_new, d_new = score(cand, gauntlet, args.confirm, args.agent, cseed, args.workers)
            s_old, _ = score(cur, gauntlet, args.confirm, args.agent, cseed, args.workers)
            if s_new > s_old:
                cur, cur_s, cur_d = cand, s, d
                seed += 1  # renova sementes da triagem para não superajustar
                cur_s, cur_d = score(cur, gauntlet, args.games, args.agent, seed, args.workers)
                msg += f'  ✔ aceito (confirmação {100 * s_old:.1f}% → {100 * s_new:.1f}%)'
                history.append({'iter': it, 'score': s_new, 'change': change})
            else:
                msg += f'  ✘ não confirmou ({100 * s_old:.1f}% vs {100 * s_new:.1f}%)'
        print(msg, flush=True)
    print(f'\nFinal: {100 * cur_s:.1f}%  {json.dumps({k: round(v, 3) for k, v in cur_d.items()})}  '
          f'({time.time() - t:.0f}s)')
    diff_add = Counter(cur) - Counter(base.cards)
    diff_rem = Counter(base.cards) - Counter(cur)
    print('Mudanças:', ', '.join([f'+{n} {label(k)}' for k, n in diff_add.items()] +
                                  [f'-{n} {label(k)}' for k, n in diff_rem.items()]) or 'nenhuma')
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(deck_to_text(cur))
    with open(args.out.rsplit('.', 1)[0] + '_history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f'Lista salva em {args.out}')


if __name__ == '__main__':
    main()
