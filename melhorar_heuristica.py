"""Melhora a IA heurística ajustando seus pesos contra o jogador aleatório.

A heurística (`ptcg/agents.py`, `HeuristicAgent`) lê os pesos de `DEFAULT_PARAMS` + `ptcg/data/heuristica.json`.
Este script faz uma busca evolutiva (1+λ, perturbação gaussiana de parte dos pesos) maximizando a taxa de vitória
da heurística contra o `RandomAgent` — em espelho e contra outro deck do conjunto —, com as MESMAS sementes para
todos os candidatos de uma geração (comparação justa). No fim valida o melhor em sementes novas e só grava se
superar os pesos atuais.

Exemplos:
    python melhorar_heuristica.py                       # 40 gerações com decks/tests/*.txt
    python melhorar_heuristica.py --avaliar             # só mede a taxa atual (validação)
    python melhorar_heuristica.py --iters 100 --games 60 --alvo 0.92
    python melhorar_heuristica.py --resetar             # volta aos pesos padrão (apaga heuristica.json)
"""
import argparse
import glob
import json
import math
import os
import random
import time
from concurrent.futures import ProcessPoolExecutor

from ptcg.agents import DEFAULT_PARAMS, PARAMS_FILE, load_params
from ptcg.decks import load_deck
from ptcg.sim import _play_one

# pesos que não devem ser tocados pela busca (limiares estruturais pequenos)
FIXOS = set()


def carregar_decks(padroes):
    arquivos = sorted(f for p in padroes for f in glob.glob(p))
    if not arquivos:
        raise SystemExit('nenhum deck encontrado')
    return [(os.path.basename(f).rsplit('.', 1)[0], load_deck(f).cards) for f in arquivos]


def montar_jobs(decks, params, jogos, seed0):
    """Heurística (com `params`) contra aleatório: espelho + contra o deck seguinte; assentos alternados."""
    spec = 'heuristic:' + json.dumps(params, sort_keys=True)
    jobs, rotulos = [], []
    n = len(decks)
    for i, (nome, d) in enumerate(decks):
        for j in {i, (i + 1) % n}:
            for k in range(jogos):
                jobs.append((d, decks[j][1], spec, 'random', seed0 + 7919 * i + 104729 * j + k, k % 2, False))
                rotulos.append(nome)
    return jobs, rotulos


def avaliar(ex, decks, params, jogos, seed0):
    jobs, rotulos = montar_jobs(decks, params, jogos, seed0)
    res = list(ex.map(_play_one, jobs, chunksize=max(1, len(jobs) // 128)))
    por = {}
    for nome, r in zip(rotulos, res):
        por.setdefault(nome, []).append(r['res'])
    medias = {k: sum(v) / len(v) for k, v in por.items()}
    total = sum(r['res'] for r in res) / len(res)
    return total, medias, len(res)


def perturbar(base, rng, sigma, frac):
    novo = dict(base)
    chaves = [k for k in base if k not in FIXOS]
    for k in rng.sample(chaves, max(1, int(len(chaves) * frac))):
        v = base[k]
        fator = math.exp(rng.gauss(0, sigma))
        delta = rng.gauss(0, sigma * 10) if abs(v) < 1 else 0
        novo[k] = (round(v * fator + delta, 2) if isinstance(v, float) or abs(v) < 3
                   else int(round(v * fator + rng.gauss(0, 1))))
    return novo


def imprimir_tabela(medias):
    for k, v in sorted(medias.items(), key=lambda kv: kv[1]):
        print(f'   {k[:36]:<36} {100 * v:5.1f}%')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--decks', nargs='*', default=['decks/tests/*.txt'], help='padrões glob de decks')
    ap.add_argument('--iters', type=int, default=40, help='gerações')
    ap.add_argument('--lam', type=int, default=8, help='candidatos por geração')
    ap.add_argument('--games', type=int, default=30, help='partidas por (deck, oponente) na busca')
    ap.add_argument('--val-games', type=int, default=150, help='partidas por (deck, oponente) na validação final')
    ap.add_argument('--sigma', type=float, default=0.25, help='intensidade da perturbação')
    ap.add_argument('--frac', type=float, default=0.25, help='fração dos pesos perturbada por candidato')
    ap.add_argument('--alvo', type=float, default=0.90, help='para quando a validação passar disso')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--workers', type=int, default=None)
    ap.add_argument('--avaliar', action='store_true', help='só mede a taxa dos pesos atuais')
    ap.add_argument('--resetar', action='store_true', help='apaga heuristica.json (volta aos padrões)')
    ap.add_argument('--sem-salvar', action='store_true')
    a = ap.parse_args()

    if a.resetar:
        if os.path.exists(PARAMS_FILE):
            os.remove(PARAMS_FILE)
        print('pesos padrão restaurados')
        return
    decks = carregar_decks(a.decks)
    workers = a.workers or max(1, (os.cpu_count() or 2) - 1)
    rng = random.Random(a.seed)
    VAL_SEED = 5_000_000          # sementes de validação nunca usadas na busca
    atual = load_params()
    t0 = time.time()
    with ProcessPoolExecutor(workers) as ex:
        v0, m0, n = avaliar(ex, decks, atual, a.val_games, VAL_SEED)
        print(f'Pesos atuais: {100 * v0:.1f}% contra o aleatório ({n} partidas, {len(decks)} decks)')
        imprimir_tabela(m0)
        if a.avaliar:
            return
        melhor, melhor_val = dict(atual), v0
        for it in range(1, a.iters + 1):
            seed0 = a.seed * 1_000_003 + it * 50_021          # mesmas partidas para toda a geração
            base_v, _, _ = avaliar(ex, decks, melhor, a.games, seed0)
            cands = [(avaliar(ex, decks, c, a.games, seed0)[0], c)
                     for c in (perturbar(melhor, rng, a.sigma, a.frac) for _ in range(a.lam))]
            v, c = max(cands, key=lambda x: x[0])
            marca = ''
            if v > base_v:
                melhor = c
                marca = ' ← aceito'
            print(f'[{it:3d}/{a.iters}] base {100 * base_v:5.1f}%  melhor candidato {100 * v:5.1f}%{marca}  '
                  f'({time.time() - t0:.0f}s)', flush=True)
            if marca and it % 5 == 0:
                vv, _, _ = avaliar(ex, decks, melhor, a.val_games, VAL_SEED)
                print(f'      validação parcial: {100 * vv:.1f}%', flush=True)
                if vv >= a.alvo:
                    break
        vf, mf, n = avaliar(ex, decks, melhor, a.val_games, VAL_SEED)
        print(f'\nValidação final (sementes novas): {100 * vf:.1f}%  (antes: {100 * v0:.1f}%)')
        imprimir_tabela(mf)
        mudou = {k: (atual[k], melhor[k]) for k in melhor if melhor[k] != atual[k]}
        if vf > v0 and not a.sem_salvar:
            with open(PARAMS_FILE, 'w', encoding='utf-8') as f:
                json.dump({k: melhor[k] for k in sorted(melhor) if melhor[k] != DEFAULT_PARAMS[k]},
                          f, indent=1, ensure_ascii=False)
            print(f'Gravado em {PARAMS_FILE} ({len(mudou)} pesos mudaram)')
        else:
            print('Sem ganho na validação: pesos mantidos.')
        if vf < a.alvo:
            print(f'Alvo de {100 * a.alvo:.0f}% não atingido — veja os decks mais fracos acima '
                  f'(o ajuste de pesos tem limite; os casos restantes pedem regras novas na heurística).')


if __name__ == '__main__':
    main()
