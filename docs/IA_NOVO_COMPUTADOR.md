# Treino da IA em outro computador — roteiro

Escrito em 2026-11-13. Objetivo: refazer a imitação com o motor e a heurística atuais e, em seguida, rodar o PPO longo.
Contexto e explicações: [`IA_TREINO.md`](IA_TREINO.md) · diário: [`IA_PROGRESSO.md`](IA_PROGRESSO.md).

## Por que refazer a imitação
Os dados e o `imitacao.pt` atuais são de 18/10, **anteriores** à correção estrutural da heurística (`a46a501`),
ao ajuste de pesos (`ptcg/data/heuristica.json`) e a ~80 correções de rulings do motor. A rede copiaria uma
heurística e regras que não existem mais. "Refazer a heurística" aqui significa **regenerar os dados com a heurística
atual e retreinar a imitação**; os pesos da heurística não mudam (já estão versionados).
Se quiser reajustar os pesos antes (`python melhorar_heuristica.py`), faça **antes** do passo 5 e dê commit em `heuristica.json`.

## O que copiar manualmente (fora do git)

| O que | Precisa? | Observação |
|---|---|---|
| `decks/limitless/` (3,3 MB, 768 decks) | **Sim**, recomendado | Está no `.gitignore`. Só `decks/tests/` (12 decks) vai pelo git. Sem essa pasta, a geração usaria 12 decks em vez de ~108 e a rede ficaria muito pior. Alternativa: `python import_limitless.py` (precisa de internet e pode trazer um conjunto diferente do atual, porque o top 8 dos torneios é baixado de novo). |
| `decks/_fora_da_rotacao/` (840 KB) | Não | Fora do formato; não entra no treino. |
| `dados/imitacao/` (5,4 GB), `checkpoints/` | **Não** | Estão desatualizados; serão regenerados. |
| `.venv/`, `.cache/`, `imagens/`, `cartas/cartas.db` | Não | Locais. O `cartas.db` é recriado sozinho; imagens não influenciam o treino. |
| Login do W&B | Opcional | Rode `wandb login` na máquina nova (servidor da CoreWeave, entidade `tiago-amorim`). Sem isso o treino roda e só avisa; o registro local em `logs/ia/treinos.jsonl` continua. |

Tudo o mais (código, `ptcg/data/*.json` incluindo `heuristica.json`, `decks/tests/`, `logs/ia/treinos.jsonl`) vem pelo git.
Antes de sair deste computador: **faça commit e push** (inclusive este documento) e copie `decks/limitless/`
(`tar czf limitless.tgz decks/limitless` → descompactar na raiz do projeto na outra máquina).

## Passo a passo

### 1. Preparar a máquina
```
git clone git@github.com:TiagoCAAmorim/poketrainer.git && cd poketrainer   # ou git pull
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # numpy, torch, wandb, pytest
# com GPU NVIDIA: instale o torch com CUDA (https://pytorch.org); confirme:
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
nvidia-smi                              # VRAM livre (o treino precisa de ~1 GB na imitação)
nproc                                   # o PPO usa 30 workers por padrão (máquina de 32 núcleos)
wandb login                             # opcional
```
Armadilhas vistas no notebook com RTX 3060 Laptop (13/11/2026):
- O `pip install torch` padrão veio para CUDA 13.2 e o driver só ia até 12.9 (`cuda.is_available() == False`).
  Resolvido com `pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cu128`.
  Confira a "CUDA Version" no topo do `nvidia-smi` e escolha a build do torch igual ou menor.
- **Alimentação do notebook**: com uma fonte fraca (mesmo aparecendo "na tomada"), a GPU ficou em `P8`, 210 MHz e
  teto de 20 W (`nvidia-smi -q -d PERFORMANCE` mostra "SW Power Cap: Active"), e a imitação rodou a ~2 passos/s.
  Trocando para a fonte original (P0, ~80 W) foi a **27 passos/s**. Confira `nvidia-smi` antes de começar.

Copie `decks/limitless/` agora e confira: `find decks -name '*.txt' | wc -l` deve dar ~924 (ou 768 + 12 + extras).

### 2. Validar o ambiente
```
python cartas.py resumo                 # 2083/2083 implementadas (gera cartas/cartas.db)
python tests/test_rules.py              # falhas: 0
python tests/test_replay.py             # ok 4 logs
python tests/test_ai.py                 # 3 linhas ok (torch/GPU funcionando)
python tests/fuzz.py --games 100        # 0 com erro
```
Se algo falhar aqui, **não siga**: o problema é de ambiente (versão do Python/torch) ou de cópia incompleta.

### 3. Gerar os dados de imitação (~2–3 min em 32 núcleos; ~5 GB em disco)
```
python imitar.py gerar --partidas 20000
```
Confirme: `dados/imitacao/erros.jsonl` não deve existir (ou estar vazio). Erro do motor aqui é bug a investigar.
Com menos núcleos o tempo cresce proporcionalmente; confira `python imitar.py gerar --help` para o número de processos.

### 4. Treinar a imitação (~10 min na RTX 4070 Ti SUPER)
```
python imitar.py treinar --epocas 6
```
Valores de referência: `val_acc` ≈ 86% e `val_mse_v` caindo (≈ 0,85). `val_mse_v` subindo = a rede está decorando; não siga.
Se `passos/s` despencar, a VRAM está cheia (outro programa na GPU) — ver `nvidia-smi`.

### 5. Medir o ponto de partida (baseline)
```
python imitar.py avaliar checkpoints/imitacao.pt --partidas 400
```
Referência antiga: 43,5% contra a heurística (±2,5%). O número novo pode diferir porque a heurística mudou.
**Anote-o em `docs/IA_PROGRESSO.md`** (nova entrada de sessão) e atualize a tabela "Referência atual".

### 6. PPO longo (~35–45 min para 300 iterações)
```
python train.py --resume checkpoints/imitacao.pt --iterations 300 --out checkpoints/ppo1
python ia.py acompanhar checkpoints/ppo1/train_log.jsonl --seguir       # outro terminal
```
- Critério principal: coluna `aval.` (vitórias contra a heurística). Meta inicial: **> 50%**.
- Saudável: `kl` < 0,02, `clip` 0,02–0,10, `ent` caindo devagar, `v` caindo.
- Se `kl` > 0,03: baixe `--lr`. Se `ent` despencar cedo: suba `--ent-coef`. Se estagnar: mais `--games` por iteração,
  `--p-heuristic` maior ou rede maior (`--hidden 512` exige refazer a imitação).
- Ctrl+C é seguro: salva `latest.pt` e registra o fim. Continuar: `--resume checkpoints/ppo1/latest.pt`.
- Sem internet: `WANDB_MODE=offline` e depois `wandb sync wandb/offline-run-*`.

### 7. Ao terminar
1. Registre números e conclusão em `docs/IA_PROGRESSO.md` e marque o item do treino longo na Fase 8 do `PLANO.md`.
2. Commit de `logs/ia/treinos.jsonl`, `IA_PROGRESSO.md` e `PLANO.md` e push.
3. Traga de volta (fora do git) o `best.pt` se quiser usá-lo neste computador:
   `checkpoints/ppo1/best.pt` → `python simulate.py <deck> <deck> --agent model:checkpoints/ppo1/best.pt`.

## Cuidados
- Não altere `ptcg/encode.py` nem a base de cartas no meio do processo: dados e checkpoints deixam de servir.
- Não misture checkpoints entre máquinas com dados gerados em versões diferentes do código: use o mesmo commit
  (`git log -1` igual) do início ao fim.
