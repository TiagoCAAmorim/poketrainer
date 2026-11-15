"""Acompanhamento dos treinos da IA (guia completo em docs/IA_TREINO.md).

    python ia.py historico [--ultimos 20] [--tipo ppo_avaliacao]     tudo que foi gerado/treinado/avaliado (logs/ia/treinos.jsonl)
    python ia.py acompanhar [checkpoints/train_log.jsonl] [--seguir]  curva da execução de PPO mais recente
    python ia.py niveis                                               níveis de dificuldade (0 = heurística … 9) em ias/
    python ia.py nivel 9 checkpoints/ppo5/t4/latest.pt --nome ppo5    guarda a rede em ias/ como nível 9
    python ia.py elo                                                  Elo (heurística = 0) de toda rede já avaliada
    python ia.py escada [--partidas 1000]                             confronto direto de cada nível contra o anterior
    python ia.py busca --agente busca:nivel:9 --oponente nivel:9      avalia a busca na hora de jogar (ptcg/ai/busca.py)
"""
import argparse
import json
import sys
import time
from pathlib import Path

from ptcg.logbook import treinos


def historico(ultimos=20, tipo=None):
    recs = [r for r in treinos() if tipo is None or r['tipo'] == tipo]
    if not recs:
        print('Nenhum treino registrado ainda (logs/ia/treinos.jsonl).')
        return
    print(f'Treinos da IA ({len(recs)} registros; últimos {min(ultimos, len(recs))}) — logs/ia/treinos.jsonl')
    for r in recs[-ultimos:]:
        print(f"  {r['quando'].replace('T', ' ')}  {r['tipo']:<14} {r['resumo']}")


def _ultima_execucao(path):
    linhas = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    ini = max((i for i, r in enumerate(linhas) if 'inicio' in r), default=-1)
    return (linhas[ini] if ini >= 0 else {}), [r for r in linhas[ini + 1:] if 'it' in r]


def _fmt(v, nd=3):
    return '' if v is None else (f'{v:.{nd}f}' if isinstance(v, float) else str(v))


def acompanhar(path, a_cada=None):
    if not Path(path).exists():
        print(f'{path} não existe: rode python train.py ... primeiro.')
        return
    cab, its = _ultima_execucao(path)
    if cab:
        print(f"Execução {cab['inicio']}: {cab.get('iterations')} iterações, {cab.get('games')} partidas/it, "
              f"{cab.get('decks')} decks, lr {cab.get('lr')}" + (f", a partir de {cab['resume']}" if cab.get('resume') else ''))
    if not its:
        print('Nenhuma iteração concluída ainda.')
        return
    evals = [(r['it'], r['eval_vs_heuristica']) for r in its if 'eval_vs_heuristica' in r]
    passo = a_cada or max(1, len(its) // 25)
    print(f"\n{'it':>5} {'min':>6} {'aval.':>6} {'treino':>7} {'kl':>7} {'clip':>6} {'ent':>6} {'v':>6} {'trans.':>7}")
    janela = []
    for r in its:
        if 'treino_vs_heuristica' in r:
            janela = (janela + [r['treino_vs_heuristica']])[-10:]
        if r['it'] % passo == 0 or 'eval_vs_heuristica' in r or r is its[-1]:
            media = sum(janela) / len(janela) if janela else None
            print(f"{r['it']:>5} {_fmt(r.get('min'), 1):>6} {_fmt(r.get('eval_vs_heuristica')):>6} "
                  f"{_fmt(media):>7} {_fmt(r.get('kl'), 4):>7} {_fmt(r.get('clip')):>6} {_fmt(r.get('ent')):>6} "
                  f"{_fmt(r.get('v')):>6} {_fmt(r.get('transicoes')):>7}")
    print(f"\naval. = vitórias contra a heurística na avaliação ({cab.get('eval_games', '?')} partidas, "
          "jogada mais provável, sementes fixas)")
    print("treino = média móvel (10 its) das vitórias contra a heurística durante o treino (com sorteio)")
    if evals:
        bi, bv = max(evals, key=lambda x: x[1])
        print(f"Melhor avaliação: {bv:.1%} na iteração {bi} ({Path(cab.get('out', 'checkpoints')) / 'best.pt'})")
        if len(evals) >= 3:
            ini, fim = evals[0][1], sum(v for _, v in evals[-3:]) / 3
            print(f"Tendência: {ini:.1%} → {fim:.1%} (média das 3 últimas avaliações)")
    alertas = []
    ult = its[-10:]
    if any(r.get('kl', 0) > 0.03 for r in ult):
        alertas.append('KL alto (> 0,03) nas últimas iterações: a política está mudando rápido demais; tente --lr menor')
    if any(r.get('erros_motor') for r in ult):
        alertas.append('erros do motor nos rollouts: rode python tests/fuzz.py e veja os decks envolvidos')
    if len(its) > 20 and its[-1].get('ent', 1) < 0.05:
        alertas.append('entropia muito baixa: a rede parou de explorar; tente --ent-coef maior')
    for a in alertas:
        print(f'⚠ {a}')


def mostrar_niveis():
    from ptcg.ai.niveis import carregar, faixa
    print(f"{'nível':>5}  {'faixa':<13} {'Elo':>5} {'× heur.':>8}  {'nome':<12} origem")
    for n in carregar():
        elo = n.get('elo')
        vs = n.get('vs_heuristica')
        print(f"{n['nivel']:>5}  {faixa(n['nivel']):<13} {'' if elo is None else f'{elo:+d}':>5} "
              f"{'' if vs is None else f'{vs:.1%}':>8}  {n['nome']:<12} {n.get('origem', '')}")
        if n.get('descricao'):
            print(f"{'':>8}{n['descricao']}")
    from ptcg.ai.niveis import _antigas
    ant = _antigas()
    if ant:
        print('\nFora da escala (guardadas em ias/, listadas em ias/antigas.json): '
              + ', '.join(f"{a['nome']} (ex-nível {a.get('ex_nivel')}, Elo {a.get('elo', '?'):+})" for a in ant))
    print('\nElo relativo à heurística, ajustado a todas as avaliações de logs/ia/treinos.jsonl '
          '(+100 ≈ 64% de vitórias, +200 ≈ 76%, +300 ≈ 85%). Na interface: "IA nível N"; no código: make_agent("nivel:N").')


def mostrar_elo():
    from ptcg.ai.niveis import confrontos, elo
    r = elo()
    n_jogos = {}
    for a, b, _, p in confrontos():
        n_jogos[a] = n_jogos.get(a, 0) + p
        n_jogos[b] = n_jogos.get(b, 0) + p
    for nome, v in sorted(r.items(), key=lambda x: -x[1]):
        print(f'{v:+7.0f}  ({n_jogos[nome]:>6} partidas)  {nome}')


def escada(partidas=1000, seed=777):
    """Cada nível contra o anterior (registrado em treinos.jsonl, entra no Elo)."""
    import subprocess
    from ptcg.ai.niveis import carregar, recalcular
    niveis = carregar()
    for ant, n in zip(niveis, niveis[1:]):
        op = 'heuristic' if not ant.get('arquivo') else f"model:{ant['arquivo']}"
        print(f"nível {n['nivel']} × nível {ant['nivel']} ({partidas} partidas)...", flush=True)
        subprocess.run([sys.executable, 'imitar.py', 'avaliar', n['arquivo'], '--oponente', op, '--partidas',
                        str(partidas), '--seed', str(seed), '--nome', f"escada_{n['nivel']}_vs_{ant['nivel']}"],
                       check=True, stdout=subprocess.DEVNULL)
    recalcular()
    mostrar_niveis()


def _spec_registro(spec: str) -> str:
    """'nivel:N' → 'model:ias/<rede>.pt' (ou 'heuristic'), para o Elo reconhecer a rede do nível."""
    from ptcg.ai.niveis import obter
    if spec.startswith('nivel:'):
        n = obter(int(spec[6:]))
        return f"model:{n['arquivo']}" if n.get('arquivo') else 'heuristic'
    return spec


def avaliar_busca(a):
    from ptcg.ai.busca import avaliar
    from ptcg.logbook import registrar_treino
    r = avaliar(a.agente, a.oponente, a.partidas, a.seed, a.processos)
    print(json.dumps(r, ensure_ascii=False))
    agente = a.agente if a.agente.startswith('busca:') else _spec_registro(a.agente)
    registrar_treino('avaliacao', f'{a.agente}: {r["vitorias"]:.1%} contra {a.oponente} '
                     f'({r["partidas"]} partidas, ±{r["erro_padrao"]:.1%})', checkpoint=agente, seed=a.seed,
                     **{**r, 'oponente': _spec_registro(a.oponente)}, **({'nome': a.nome} if a.nome else {}))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('historico')
    p.add_argument('--ultimos', type=int, default=20)
    p.add_argument('--tipo', default=None,
                   help='dados | imitacao | avaliacao | ppo_inicio | ppo_avaliacao | ppo_fim')
    p = sub.add_parser('acompanhar')
    p.add_argument('arquivo', nargs='?', default='checkpoints/train_log.jsonl')
    p.add_argument('--a-cada', type=int, default=None, help='mostrar uma linha a cada N iterações')
    p.add_argument('--seguir', action='store_true', help='atualiza a cada 60 s (Ctrl+C para sair)')
    sub.add_parser('niveis')
    p = sub.add_parser('nivel')
    p.add_argument('nivel', type=int)
    p.add_argument('checkpoint')
    p.add_argument('--nome', required=True)
    p.add_argument('--descricao', default='')
    sub.add_parser('elo')
    p = sub.add_parser('escada')
    p.add_argument('--partidas', type=int, default=1000)
    p = sub.add_parser('busca', help='avalia um agente com busca (ou qualquer agente de make_agent)')
    p.add_argument('--agente', default='busca:nivel:9', help="ex.: 'busca:nivel:9|mundos=16,limiar=0.8'")
    p.add_argument('--oponente', default='nivel:9')
    p.add_argument('--partidas', type=int, default=400)
    p.add_argument('--seed', type=int, default=777)
    p.add_argument('--processos', type=int, default=None)
    p.add_argument('--nome', default=None, help='rótulo no registro (logs/ia/treinos.jsonl)')
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)
    if a.cmd == 'historico':
        historico(a.ultimos, a.tipo)
    elif a.cmd == 'niveis':
        from ptcg.ai.niveis import recalcular
        recalcular()
        mostrar_niveis()
    elif a.cmd == 'nivel':
        from ptcg.ai.niveis import definir
        definir(a.nivel, a.checkpoint, a.nome, a.descricao)
        mostrar_niveis()
    elif a.cmd == 'elo':
        mostrar_elo()
    elif a.cmd == 'escada':
        escada(a.partidas)
    elif a.cmd == 'busca':
        avaliar_busca(a)
    elif a.cmd == 'acompanhar':
        while True:
            acompanhar(a.arquivo, a.a_cada)
            if not a.seguir:
                break
            try:
                time.sleep(60)
            except KeyboardInterrupt:
                break
            print('\n' + '=' * 70)


if __name__ == '__main__':
    main()
