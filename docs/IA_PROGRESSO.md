# Treino da IA — progresso

Diário dos experimentos (o que foi tentado, números e conclusões). Como funciona e comandos:
[`IA_TREINO.md`](IA_TREINO.md). Registro automático de cada execução: `logs/ia/treinos.jsonl`
(`python ia.py historico`); curva do PPO em andamento: `python ia.py acompanhar`; gráficos de todas as execuções no
W&B: https://forge.coreweave.com/wandb/tiago-amorim/poketrainer

## Como retomar
1. `python ia.py historico` — o que já foi feito e o último resultado.
2. Se o PPO estiver rodando ou acabou de rodar: `python ia.py acompanhar` (curva e alertas).
3. Ao terminar um experimento, acrescentar uma entrada abaixo: o que mudou, os números (vitórias contra a heurística
   com o erro padrão) e a conclusão. Atualizar também `PLANO.md` (Fase 8) se mudar o estado da fase.

## Referência atual
| Rede | Vitórias contra a heurística | Como foi obtida |
|---|---|---|
| `checkpoints/imitacao.pt` | **43,5–44%** (400 partidas, ±2,5%) | imitação, 20 mil partidas, 6 épocas, `detach_value` |
| `checkpoints/best.pt` | — (PPO longo ainda não rodado) | — |

## Sessões

### Sessão 1 (2026-10-18): pipeline montado e primeiros números
Ambiente: PyTorch 2.14 + CUDA, RTX 4070 Ti SUPER (16 GB, compartilhada com `~/dev/graph_nn`), 32 núcleos, WSL.

- **PPO original** (`train.py` de 1 processo): rodava, mas partindo do zero ganhava 0% da heurística e o rollout de
  240 partidas levaria ~70 s por iteração. Decisão: pré-treinar por imitação e paralelizar os rollouts.
- **Dados**: 5 mil partidas → 796 mil decisões em 39 s; depois +15 mil (seed 1) → total **20 mil partidas,
  3,17 milhões de decisões**, 108 decks, epsilon 5%. Média de 6,7 opções por decisão (máx. 49).
- **Bug do motor achado pelo treino**: Night Joker (N's Zoroark ex) oferecia o Night Joker de outro N's Zoroark ex no
  Banco e a cópia se repetia sem fim (RecursionError). Eram as 8 partidas com erro da 1ª geração; corrigido
  (`not_in_copy_chain` em `ptcg/effects/extra.py`, teste em `tests/test_rules.py`). Gerações seguintes: 0 erros.
- **Imitação, experimento A** (5 mil partidas, 8 épocas, `vf_coef` 0,5): `val_acc` 84%, mas `val_mse_v` subiu de
  0,78 para 1,06 (treino 0,05) — o valor decorava as partidas.
- **Imitação, experimento B** (20 mil partidas, 6 épocas, `vf_coef` 0,25): `val_acc` **85,9%**, `val_mse_v`
  0,74 → 0,98 (ainda decorando) → **38,3%** contra a heurística (400 partidas, ±2,4%).
- **Imitação, experimento C** (igual a B + `detach_value`): `val_acc` **86,1%**, `val_mse_v` 0,88 → **0,85**
  (caindo a cada época, sem decorar) → **44,0%** contra a heurística (±2,5%). Virou o padrão.
  Reavaliado depois com outras sementes: 43,5%.
- **Travamento por GPU cheia**: com o treino de imitação + um teste de PPO + os processos do `graph_nn`, a VRAM
  acabou e o treino quase parou (35 min sem completar uma época). Sozinho: ~37 ms/passo, 721 MB de pico. Foi acrescentado
  o progresso dentro da época (`passos/s`) para perceber isso cedo.
- **PPO paralelo, teste de 10 iterações** a partir do experimento C (240 partidas/it, 30 workers): ~7 s por iteração
  (3,5 s rollout + 2,7 s atualização, ~30 mil decisões), KL 0,003–0,007, `clip` ~2%. Avaliação contra a heurística
  (400 partidas): 44,0% → 44,9% (it 5) → 46,6% (it 10) — dentro do ruído; estável.
- **W&B**: treinos passam a ser registrados em tiago-amorim/poketrainer (CoreWeave). 1ª execução:
  `avaliacao_imitacao_inicial` — `imitacao.pt` com 43,5% contra a heurística (400 partidas).

**Próximo**: PPO longo (`python train.py --resume checkpoints/imitacao.pt --iterations 300`) e acompanhar
`aval.`; meta inicial: passar de 50% contra a heurística. Ideias se estagnar: mais partidas por iteração, `--lr`
menor, `--p-heuristic` maior, rede maior (`--hidden 512` exige refazer a imitação).
