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
| `checkpoints/imitacao.pt` | **48,7%** (400 partidas, ±2,5%) | imitação refeita em 13/11 (motor e heurística atuais), 20 mil partidas, 780 decks, 6 épocas, `detach_value` |
| `checkpoints/ppo4/t2/latest.pt` | **85,0%** (2000 partidas, ±0,8%); vence o `ppo2` em 60,0% e o `ppo1` em 69,1% | `ppo2` + 100 it (`lr_decai`) + 250 it (`ppo3/t1`) + 60 it e 200 it com `--games 960` (`plato/lote960`, `ppo4`) |
| `checkpoints/ppo2/latest.pt` | 79,7% (2000 partidas, ±0,9%); vence o `ppo1` em 58,7% | `ppo1` (300 it) + `sweep1/g480` (30 it) + `ppo2` (400 it), padrões do `train.py` |
| `checkpoints/ppo1/latest.pt` | 73,4% (1000 partidas, ±1,4%) | PPO 300 it a partir da imitação |

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

### Sessão 2 (2026-11-13): imitação refeita em outra máquina
Ambiente: notebook com RTX 3060 Laptop (6 GB), 20 núcleos, 15 GB de RAM, WSL; PyTorch 2.11 + cu128 (o torch padrão,
cu132, não enxergava a GPU com o driver 12.9). Roteiro: [`IA_NOVO_COMPUTADOR.md`](IA_NOVO_COMPUTADOR.md).
Motivo: dados e rede da sessão 1 eram anteriores à correção estrutural da heurística (`a46a501`), ao ajuste de pesos e
a ~80 correções de rulings do motor.

- **Dados**: 20 mil partidas → **2,86 milhões de decisões**, **780 decks** (768 do Limitless + 12 de `decks/tests/`;
  na sessão 1 eram 108), epsilon 5%, **0 erros do motor**, 165 empates. ~10 min com 18 processos.
- **Fonte de alimentação fraca**: na 1ª época a GPU ficou em P8 / 210 MHz / teto de 20 W ("SW Power Cap") e o treino
  andou a ~2 passos/s (34 min na época 1). Com a fonte original (P0, ~80 W): **27 passos/s, ~98 s por época**.
- **Imitação** (6 épocas, `vf_coef` 0,25, `detach_value`): `val_acc` 82,9 → 84,5 → 85,2 → 85,6 → 85,9 → **86,0%**;
  `val_mse_v` 0,836 → 0,821 → 0,806 → 0,797 → 0,792 → **0,790** (caindo em todas as épocas, sem decorar).
- **Referência**: `imitacao.pt` com **48,7%** contra a heurística (400 partidas, ±2,5%; 51,8% indo primeiro). A
  avaliação embutida no fim do treino deu 46,3% (200 partidas, ±3,5%). Melhor que os 43,5% da sessão 1, mas a
  heurística e o conjunto de decks mudaram, então os números não são diretamente comparáveis.
- **PPO longo `ppo1`** (`train.py --resume checkpoints/imitacao.pt --iterations 300 --out checkpoints/ppo1`, padrões:
  lr 1e-4, ent 0,005, 240 partidas/it, 18 workers): **47 min** (~9,5 s/it), 0 erros do motor.
  Avaliação embutida (200 partidas, semente 12345): 46,3% (it 0) → 57,3% (40) → 60,5% (60) → 63,2% (100) →
  68,0% (160) → 72,8% (200) → 74,3% (260, `best.pt`) → 68,8% (300). `kl` 0,001 → pico 0,023 (it 40) → 0,009–0,013;
  `clip` 0,04 → 0,07; **`ent` subiu** 0,23 → 0,18 (it 40) → 0,31 (it 300); `v` ~0,12–0,14.
  Reavaliação sem viés de seleção (1000 partidas, semente 777): `imitacao.pt` **46,3%** ±1,6% ·
  `ppo1/best.pt` **72,8%** ±1,4% · `ppo1/latest.pt` **73,4%** ±1,4%.
  Conclusão: o PPO passou a heurística com folga (+27 pontos), mas a curva achatou em ~72% depois da it 200 e a
  entropia não para de subir. Próximo: varredura curta de hiperparâmetros a partir de `ppo1/latest.pt` antes de outro
  treino longo.
- **Varredura `sweep1`** (60 it cada a partir de `ppo1/latest.pt`, que mede 73,9% em 2000 partidas; avaliação final
  de 2000 partidas, semente 777, ±1,0%; `g480` com 30 it para o mesmo total de partidas):

  | Rodada | Mudança | Vitórias | `kl` | `ent` (it 60) |
  |---|---|---|---|---|
  | `g480` | 480 partidas/it | **77,5%** | 0,012 | 0,31 |
  | `base` | — | **77,3%** | 0,011 | 0,33 |
  | `lr5e5` | lr 5e-5 | 75,9% | 0,005 | 0,28 |
  | `base_s1` | — (semente 1) | 75,7% | — | — |
  | `ph50` | `--p-heuristic` 0,5 | 75,4% | — | — |
  | `ent0` | `--ent-coef` 0 | 75,1% | 0,013 | 0,26 |
  | `mg1` | `--max-grad` 1,0 | 75,0% | — | — |
  | `lr2e4` | lr 2e-4 | 72,9% | 0,023 | 0,42 |

  Métricas novas: `var_explicada` ≈ 0,73 (o valor funciona); `grad_norm` ≈ 0,65 antes do corte, ou seja, o
  `--max-grad` 0,5 corta quase todo passo (afrouxar para 1,0 não ajudou). A entropia subindo vem do tamanho do passo
  (lr maior → entropia maior) e, em parte, do bônus de entropia.
  Conclusão: `base` e `base_s1` diferem 1,6 ponto só pela semente, e tudo menos `lr2e4` fica nessa faixa. **Os padrões
  do `train.py` estão adequados**; ajustar hiperparâmetros não é o gargalo. Todas as rodadas ganharam 1–3,5 pontos em
  60 it, então treinar mais ainda rende. Próximo: testar capacidade (`--hidden 512`).
- **Rede maior (`--hidden 512`, 5,9 M de pesos)**: imitação nos mesmos dados (6 épocas, ~3,5 min/época, 12 passos/s):
  `val_acc` **86,2%**, `val_mse_v` 0,788 (256: 86,0% / 0,790) → **46,5%** contra a heurística (1000 partidas;
  256: 46,3%). PPO com os padrões (`checkpoints/ppo_h512`, ~15,7 s/it, 1,65× a 256), interrompido na it 200: a
  avaliação embutida (200 partidas, semente 12345) ficou 3–9 pontos abaixo do `ppo1` da it 50 à 200 (63,2% contra
  72,8% na it 200), mas a reavaliação com 2000 partidas (semente 777) deu **73,2%** — igual ao `ppo1` na it 300
  (73,4–73,9%). `grad_norm` 0,3–0,55 (menos corte que a 256); `kl` um pouco maior (0,015–0,025).
  Conclusões: (1) **capacidade não é o gargalo**: por tempo de máquina as duas empatam; fica a 256. (2) **A avaliação
  embutida de 200 partidas engana** (poucos decks dos 780 entram nela): decidir só com ≥ 1000 partidas; os treinos
  seguintes usam `--eval-games 600`. Interromper a 512 pela curva embutida foi precipitado.
- **`--lr-final`** (novo em `train.py`): decaimento linear da lr ao longo das iterações da execução.
- **PPO longo `ppo2`** (400 it a partir de `sweep1/g480/latest.pt`, padrões, `--eval-games 600`): **72 min**.
  Avaliação embutida (600 partidas): 76,0% (it 0) → 73–77% (it 10–90) → 79,2% (100) → 73,6–77,9% (150–250) →
  79,0% (300) → 81,8% (380, `best.pt`) → 79,2% (400). `kl` 0,010–0,013, `ent` 0,31 → 0,36, `grad_norm` ~0,7,
  `var_explicada` 0,72–0,79.
  Reavaliação (semente 777): `ppo2/latest.pt` **79,7%** ±0,9% (2000 partidas) · `ppo2/best.pt` 78,2% (o máximo da
  curva embutida volta a enganar). **Confronto direto** (novo, `--oponente model:`; 1000 partidas, ±1,6%):
  `ppo2` × sua it 200 **55,0%** · `ppo2` × `ppo1/latest` **58,7%** · (`ppo2` it 200 × `ppo1` 57,0%, 400 partidas;
  `ppo1` × `imitacao` 79,2%, 200 partidas).
  Conclusão: contra a heurística a curva quase estaciona (~76–80%), mas o confronto direto mostra que a rede segue
  melhorando — a heurística deixou de ser uma régua sensível. Usar confrontos entre versões para medir progresso.
- **Decaimento da lr** (100 it a partir de `ppo2/latest.pt` cada; 2000 partidas contra a heurística, ±0,9%;
  confrontos com 1000, ±1,6%):

  | Rodada | Heurística | × `ppo2` | × a outra |
  |---|---|---|---|
  | `lr_const` (1e-4) | 80,3% | 50,2% | — |
  | `lr_decai` (1e-4 → 1e-5, `--lr-final`) | 81,0% | 53,7% | 49,5% |

  Com a lr no fim do decaimento o `kl` cai a 0,0006 e o `clip` a 0,006 (a rede quase não muda). Conclusão: sem ganho
  claro (confronto direto entre as duas empata). **Mais importante: os ganhos minguam** — 100 it a mais empatam com o
  `ppo2`. Suspeita: o pool de oponentes só tem as 5 últimas versões (todas das últimas ~100 it), e os confrontos
  sugerem ciclos (it 200 × `ppo1` 57%, final × it 200 55%, mas final × `ppo1` só 58,7%).
- **`--pool-inicial`** (novo em `train.py`): checkpoints antigos (inclusive de outra arquitetura) ficam no pool de
  oponentes a execução inteira; são copiados para `_pool/fixo_*.pt`, e a poda só apaga snapshots.
- **Pool diverso `pool_div`** (100 it a partir de `ppo2/latest.pt`, `--p-pool 0.3`, `--pool-inicial` com `ppo1`,
  `ppo2` it 200, `sweep1/g480` e `ppo_h512`): heurística 79,3% · × `ppo2` **49,5%** · × `lr_const` 47,4%.
  Conclusão: diversidade de oponentes também não destrava. Hiperparâmetros, capacidade, decaimento da lr e pool
  empatam em janelas de 100 it; o que rende é tempo de treino (~+5 pontos de confronto direto a cada 200 it no `ppo2`).
- **`ppo3` — platô**: trecho 1 (250 it com os padrões, a partir de `lr_decai/latest.pt`): × ponto de partida
  **49,5%**, heurística 78,6% (1000 partidas); `ent` 0,35 → 0,40. Os outros 3 trechos foram cancelados.
- **Lote grande `plato/lote960`** (60 it com `--games 960` a partir de `ppo3/t1`, mesmo total de partidas que os
  250 it acima): × `ppo3/t1` **55,5%** ±1,6% (3,4 erros padrão), heurística **84,8%** (1000 partidas; embutida 82,1% →
  83,5%). `kl` 0,014–0,015, `clip` 0,10, ~34 s/it (21 s rollout + 13 s atualização, ~115 mil transições/it).
  Conclusão: **no platô, o lote maior destrava** (com 240 partidas/it o mesmo número de partidas empatou). Na
  varredura do início (`g480`, longe do platô) não fez diferença — o ruído do gradiente só domina quando o sinal fica
  fraco. O teste `ent0` foi cancelado para dar tempo ao treino longo.
- **`ppo4`** (`--games 960`, trechos de 100 it, ~59 min cada, a partir de `plato/lote960`): × trecho anterior
  **52,4%** (t1) e **52,6%** (t2); avaliação embutida 81–84%; `kl` 0,013–0,014, `ent` 0,43 → 0,50, `var_explicada`
  0,75–0,78. `ppo4/t2/latest.pt` (200 it): heurística **85,0%** ±0,8% (2000 partidas) · × `ppo3/t1` 58,7% ·
  × `ppo2` **60,0%** · × `ppo1` **69,1%** · × `imitacao` 86,7% (1000 partidas cada, ±1,5%).
  Trecho 3 (mais 100 it) em andamento no fim da sessão.

**Resumo da sessão 2**: imitação refeita (48,7%) → `ppo1` (73,4%) → `ppo2` (79,7%) → platô em ~79% com 240
partidas/it → lote de 960 partidas/it → `ppo4` (**85,0%** contra a heurística; vence o `ppo1` em 69% e o `ppo2` em 60%).
O que não ajudou: lr maior/menor, `ent-coef` 0, `p-heuristic` 0,5, `max-grad` 1,0, rede 512, decaimento da lr, pool
de oponentes diverso. Ferramentas novas: métricas extras no W&B, `--oponente model:`, `--lr-final`, `--pool-inicial`.

**Próximo**: (1) continuar o `ppo4` com `--games 960` (ou 1920) enquanto o confronto direto contra o trecho anterior
ficar acima de 50%; (2) medir com confrontos diretos (a heurística já não discrimina bem); (3) se estacionar de novo,
suspeitar da observação (`encode.py`: o descarte ocupa 46% dos pesos como contagem por carta) ou partir para busca
na hora de jogar (a rede como guia de uma busca curta com `Game.clone()`).
