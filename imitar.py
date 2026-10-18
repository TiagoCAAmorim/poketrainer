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
from ptcg.logbook import registrar_treino


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
    for p in sub.choices.values():
        p.add_argument('--sem-wandb', action='store_true', help='não registrar no W&B (tiago-amorim/poketrainer)')
        p.add_argument('--nome', default=None, help='nome da execução no W&B')
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)   # progresso visível mesmo redirecionado para arquivo

    from ptcg.ai import wb as W
    cfg = {k: v for k, v in vars(a).items() if k not in ('cmd', 'sem_wandb', 'nome')}
    run = W.start({'gerar': 'dados', 'treinar': 'imitacao', 'avaliar': 'avaliacao'}[a.cmd], cfg, name=a.nome,
                  enabled=not a.sem_wandb)
    extra = {'wandb': run.url} if run else {}
    ok = False
    try:
        if a.cmd == 'gerar':
            from ptcg.ai.dataset import generate
            decks = decks_from(a)
            print(f'Gerando {a.partidas} partidas com {len(decks)} decks → {a.saida}')
            st = generate(a.saida, a.partidas, decks, epsilon=a.epsilon, workers=a.processos,
                          games_per_shard=a.por_shard, seed=a.seed)
            print(f'Pronto: {st}')
            run.summary({'partidas': st['games'], 'amostras': st['samples'], 'erros_motor': st['errors'],
                         'empates': st['draws'], 'decks': len(decks)})
            registrar_treino('dados', f'{st["games"]} partidas, {st["samples"]} decisões → {a.saida}',
                             saida=a.saida, partidas=st['games'], amostras=st['samples'], erros=st['errors'],
                             empates=st['draws'], decks=len(decks), epsilon=a.epsilon, seed=a.seed, **extra)
        elif a.cmd == 'treinar':
            from ptcg.ai.imitate import train_imitation
            _, res = train_imitation(a.dados, a.saida, epochs=a.epocas, batch=a.lote, lr=a.lr, hidden=a.hidden,
                                     emb=a.emb, resume=a.resume, device=a.device, eval_games=a.avaliar,
                                     vf_coef=a.vf_coef, wb=run)
            be, av = res['melhor_epoca'] or {}, res['avaliacao']
            run.summary({**{f'melhor/{k}': v for k, v in be.items()},
                         **({'aval/vitorias': av['vitorias']} if av else {}), 'amostras_treino': res['amostras_treino']})
            run.artifact(a.saida, 'imitacao', metadata={**be, **({'vitorias': av['vitorias']} if av else {})},
                         aliases=['latest'])
            registrar_treino('imitacao', f'{a.saida}: acerto {be.get("val_acc", be.get("treino_acc"))} (época '
                             f'{be.get("epoca")})' + (f', {av["vitorias"]:.1%} contra a heurística' if av else ''),
                             **res, **extra)
        elif a.cmd == 'avaliar':
            import numpy as np
            from ptcg.ai.imitate import evaluate_parallel
            from ptcg.ai.model import load_checkpoint
            net, meta = load_checkpoint(a.checkpoint, 'cpu')
            print(f'{a.checkpoint}: {json.dumps({k: v for k, v in meta.items() if k != "decks"}, ensure_ascii=False)}')
            decks = decks_from(a)
            r, por_deck = evaluate_parallel(net, decks, a.partidas, a.oponente, a.processos, a.seed, log=print,
                                            detalhes=True)
            print(json.dumps(r, ensure_ascii=False))
            run.summary({'checkpoint': a.checkpoint, **r})
            run.table('por_deck', ['deck', 'partidas', 'vitorias'],
                      [[d, len(v), float(np.mean(v))] for d, v in sorted(por_deck.items())])
            registrar_treino('avaliacao', f'{a.checkpoint}: {r["vitorias"]:.1%} contra {a.oponente} '
                             f'({r["partidas"]} partidas, ±{r["erro_padrao"]:.1%})', checkpoint=a.checkpoint,
                             decks=len(decks), seed=a.seed, **r, **extra)
        ok = True
    finally:
        run.finish(0 if ok else 1)

if __name__ == '__main__':
    main()
