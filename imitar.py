"""Pré-treino da rede por imitação da heurística (destilação) — passo anterior ao PPO (train.py).

    python imitar.py gerar --partidas 5000                      partidas heurística × heurística → dados/imitacao/
    python imitar.py treinar --epocas 8                         rede → checkpoints/imitacao.pt
    python imitar.py avaliar checkpoints/imitacao.pt --partidas 400 [--oponente heuristic|random]
    python train.py --resume checkpoints/imitacao.pt            depois: self-play com PPO

Decks: padrão = todos os decks de decks/ (inclui decks/limitless/ se tiver importado);
--pasta tests usa só os 12 fixos, --decks escolhe nomes específicos.
"""
import argparse
import json
import sys

from ptcg.decks import list_decks


def decks_from(a):
    if a.decks:
        return a.decks
    return list_decks(a.pasta) if a.pasta else list_decks()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    def deck_args(p):
        p.add_argument('--decks', nargs='+', default=None)
        p.add_argument('--pasta', default=None, help='subpasta de decks/ (ex.: tests, limitless)')

    p = sub.add_parser('gerar', help='gera partidas da heurística (acrescenta shards à pasta)')
    deck_args(p)
    p.add_argument('--partidas', type=int, default=5000)
    p.add_argument('--epsilon', type=float, default=0.05, help='chance de jogada aleatória executada')
    p.add_argument('--processos', type=int, default=None)
    p.add_argument('--por-shard', type=int, default=100)
    p.add_argument('--seed', type=int, default=0, help='use sementes diferentes ao acrescentar mais dados')
    p.add_argument('--saida', default='dados/imitacao')

    p = sub.add_parser('treinar', help='treino supervisionado nos shards')
    p.add_argument('--dados', default='dados/imitacao')
    p.add_argument('--saida', default='checkpoints/imitacao.pt')
    p.add_argument('--epocas', type=int, default=8)
    p.add_argument('--lote', type=int, default=1024)
    p.add_argument('--lr', type=float, default=1e-3)
    p.add_argument('--hidden', type=int, default=256)
    p.add_argument('--emb', type=int, default=48)
    p.add_argument('--vf-coef', type=float, default=0.25, help='peso da perda de valor (alto = decora as partidas)')
    p.add_argument('--resume', default=None)
    p.add_argument('--device', default=None)
    p.add_argument('--avaliar', type=int, default=200, help='partidas contra a heurística no fim (0 = não)')

    p = sub.add_parser('avaliar', help='taxa de vitória de um checkpoint')
    p.add_argument('checkpoint')
    deck_args(p)
    p.add_argument('--partidas', type=int, default=400)
    p.add_argument('--oponente', default='heuristic', choices=['heuristic', 'random'])
    p.add_argument('--processos', type=int, default=None)
    p.add_argument('--seed', type=int, default=12345)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)   # progresso visível mesmo redirecionado para arquivo

    if a.cmd == 'gerar':
        from ptcg.ai.dataset import generate
        decks = decks_from(a)
        print(f'Gerando {a.partidas} partidas com {len(decks)} decks → {a.saida}')
        st = generate(a.saida, a.partidas, decks, epsilon=a.epsilon, workers=a.processos,
                      games_per_shard=a.por_shard, seed=a.seed)
        print(f'Pronto: {st}')
    elif a.cmd == 'treinar':
        from ptcg.ai.imitate import train_imitation
        train_imitation(a.dados, a.saida, epochs=a.epocas, batch=a.lote, lr=a.lr, hidden=a.hidden, emb=a.emb,
                        resume=a.resume, device=a.device, eval_games=a.avaliar, vf_coef=a.vf_coef)
    elif a.cmd == 'avaliar':
        from ptcg.ai.imitate import evaluate_parallel
        from ptcg.ai.model import load_checkpoint
        net, extra = load_checkpoint(a.checkpoint, 'cpu')
        print(f'{a.checkpoint}: {json.dumps({k: v for k, v in extra.items() if k != "decks"}, ensure_ascii=False)}')
        r = evaluate_parallel(net, decks_from(a), a.partidas, a.oponente, a.processos, a.seed, log=print)
        print(json.dumps(r, ensure_ascii=False))


if __name__ == '__main__':
    main()
