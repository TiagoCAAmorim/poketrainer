"""Testa decks entre si e mostra a matriz de confrontos.

Exemplos:
    python simulate.py charizard_pidgeot raging_bolt_ogerpon --games 400
    python simulate.py decks/*.txt --games 200 --agent heuristic
    python simulate.py meu_deck.txt dragapult --agent model:checkpoints/best.pt
"""
import argparse
import json
import time

from ptcg.decks import list_decks, load_deck
from ptcg.logbook import SessaoSimulacao, registrar
from ptcg.sim import run_matchup


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('decks', nargs='*', help='arquivos .txt ou nomes em decks/ (padrão: todos)')
    ap.add_argument('--games', type=int, default=200, help='partidas por confronto')
    ap.add_argument('--agent', default='heuristic', help="'heuristic', 'random' ou 'model:arquivo.pt'")
    ap.add_argument('--agent-b', default=None, help='agente do segundo deck (padrão = --agent)')
    ap.add_argument('--workers', type=int, default=None)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--json', default=None, help='salva resultados completos em JSON')
    ap.add_argument('--salvar-log', action='store_true',
                    help='grava todas as partidas (reproduzíveis) em logs/simulacoes/')
    args = ap.parse_args()

    names = args.decks or list_decks()
    decks = {load_deck(n).name: load_deck(n).cards for n in names}
    keys = list(decks)
    spec_b = args.agent_b or args.agent
    results = {}
    t = time.time()
    sess = SessaoSimulacao('_x_'.join(k.split('/')[-1] for k in keys)[:60]) if args.salvar_log else None
    pairs = [(a, b) for i, a in enumerate(keys) for b in keys[i + 1:]] if len(keys) > 1 else [(keys[0], keys[0])]
    for a, b in pairs:
        r = run_matchup(decks[a], decks[b], args.games, args.agent, spec_b, args.seed, args.workers,
                        log_session=sess, labels=(a, b))
        results[f'{a} vs {b}'] = {k: v for k, v in r.items() if k != 'raw'}
        print(f'{a:>24} vs {b:<24} {100 * r["winrate"]:5.1f}% ±{100 * r["ci95"]:.1f}  '
              f'(1º: {100 * r["wr_going_first"]:.0f}%  2º: {100 * r["wr_going_second"]:.0f}%  '
              f'turnos≈{r["avg_turns"]:.1f}  prêmios {r["avg_prizes_a"]:.1f}-{r["avg_prizes_b"]:.1f})')
    if len(keys) > 2:
        print('\nMatriz (vitória da linha contra a coluna):')
        w = max(len(k) for k in keys)
        print(' ' * (w + 2) + ''.join(f'{k[:10]:>12}' for k in keys))
        for a in keys:
            row = []
            for b in keys:
                if a == b:
                    row.append(f'{"—":>12}')
                elif f'{a} vs {b}' in results:
                    row.append(f'{100 * results[f"{a} vs {b}"]["winrate"]:11.1f}%')
                else:
                    row.append(f'{100 - 100 * results[f"{b} vs {a}"]["winrate"]:11.1f}%')
            print(f'{a:>{w}}  ' + ''.join(row))
    print(f'\n{len(pairs) * args.games} partidas em {time.time() - t:.1f}s')
    if sess is not None:
        print(f'Partidas gravadas em {sess.path}')
    registrar('simulacao', f'{len(pairs) * args.games} partidas: ' + ', '.join(
        f'{k}={100 * v["winrate"]:.1f}%' for k, v in results.items()), agente=args.agent,
        arquivo=str(sess.path) if sess else None)
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
