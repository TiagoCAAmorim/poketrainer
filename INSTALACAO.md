# Instalação e testes — passo a passo

Siga na ordem. Cada passo diz o que deve aparecer; se algo diferente aparecer, anote a mensagem.
Nos comandos, use `python` (Linux/macOS) ou `py` (Windows, se `python` não funcionar).

## 1. Pré-requisitos

| O quê | Como conferir | Esperado |
|---|---|---|
| Python 3.10 ou mais novo | `python --version` | `Python 3.10.x` ou maior (testado no 3.13) |
| Git | `git --version` | qualquer versão |
| Navegador | — | Chrome, Edge ou Firefox (para a interface) |

Se não tiver Python: https://www.python.org/downloads/ (no Windows marque **"Add python.exe to PATH"**).

## 2. Baixar o projeto

```
git clone https://github.com/TiagoCAAmorim/poketrainer
cd poketrainer
```

## 3. Ambiente virtual (recomendado) e dependências

```
python -m venv .venv
```
Ative o ambiente:
- Windows (PowerShell): `.venv\Scripts\Activate.ps1`
  (se der erro de política: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` e tente de novo)
- Windows (cmd): `.venv\Scripts\activate.bat`
- Linux/macOS: `source .venv/bin/activate`

Instale:
```
pip install numpy
```
O motor, a biblioteca de cartas, os decks, o LOG, os testes e a interface só precisam de **numpy**.
O PyTorch (`pip install torch`) só é necessário mais tarde, para treinar a IA — pode pular por enquanto.

## 4. Testes (nesta ordem)

| # | Comando | Tempo | Resultado esperado | O que verifica |
|---|---|---|---|---|
| 1 | `python tests/test_rules.py` | < 1 s | 15 linhas `ok …` e `falhas: 0` | regras básicas (dano, fraqueza, condições, Habilidades, Ferramentas…) |
| 2 | `python tests/test_limitless.py` | < 1 s | `ok` | leitura das páginas da Limitless |
| 2c | `python tests/test_explorer.py` | < 5 s | `ok` | filtros e detalhe da página de cartas |
| 2b | `python tests/test_deckbuilder.py` | < 5 s | `ok` | busca, salvar e duplicar do montador de decks |
| 3 | `python tests/test_engine.py` | ~10 s | `ok 6.0 s` (o tempo varia) | partidas inteiras com os 12 decks top 8, sem cartas perdidas/duplicadas; partidas reproduzíveis |
| 4 | `python tests/test_replay.py` | ~10–30 s | `ok 4 logs` | as 4 partidas reais do Pokémon TCG Live são refeitas jogada a jogada |
| 5 | `python tests/fuzz.py --games 300` | ~15 s | `300 partidas, 0 com erro; …` | decks aleatórios e jogadas aleatórias (estresse do motor) |

Se `pip install pytest` estiver disponível, `python -m pytest -q tests` roda os mesmos testes de uma vez.

## 5. Conferir as ferramentas

| Comando | Esperado |
|---|---|
| `python cartas.py resumo` | na 1ª vez: `Biblioteca ainda não gerada; criando…` (gera `cartas/cartas.db`); depois a contagem por pasta e `Total: 2083 cartas` |
| `python cartas.py mostrar TWM-130` | ficha do Dragapult ex, com os ataques em inglês e português |
| `python cartas.py buscar "Ultra Bola"` | `MEG-131  Ultra Ball  Ultra Bola  Treinadores/Itens` |
| `python gerenciar_decks.py validar --todos` | `N/N válidos` (inclui os 12 decks fixos de `decks/tests/`; decks de torneios fora da rotação aparecem inválidos — use `limpar_decks.py`) |
| `python gerenciar_decks.py mostrar 01_hedrick_dragapult` | lista do 1º lugar do Mundial (`decks/tests/`) e `✔ deck válido` |
| `python gerenciar_logs.py listar` | 4 partidas do TCG Live com `✔` |
| `python simulate.py 01_hedrick_dragapult 05_heiremans_crustle --games 50` | taxa de vitória do confronto (a IA heurística ainda é simples: números indicativos) |

## 6. Interface gráfica

```
python server.py
```
Abre `http://localhost:8765` no navegador (se não abrir sozinho, digite o endereço). Teste:
1. Escolha dois decks, deixe J1 = **Humano** e J2 = **IA heurística**, clique **Nova partida** e jogue alguns turnos.
2. **Log do TCG Live…** → cole o conteúdo de `tests/fixtures/ptcgl_logs/dipplin-vs-mega-excadrill.log`
   → **Reproduzir**: deve mostrar `Ações reproduzidas: 89/89` e permitir avançar jogada a jogada.
3. **Decks…** → cole uma lista exportada do TCG Live e salve (vai para `decks/meus/`).

Para parar o servidor: `Ctrl+C` no terminal.

## 7. Seus próprios dados

- **Seus decks**: no TCG Live, exporte a lista (copiar) e salve num arquivo `.txt`; depois
  `python gerenciar_decks.py criar nome_do_deck --arquivo lista.txt`.
- **Suas partidas**: no TCG Live, no histórico da partida use **Copy Log**, salve num `.txt` e rode
  `python gerenciar_logs.py importar partida.txt`. O resultado mostra se o motor refez todas as jogadas;
  se aparecer `Divergência: …`, esse log é exatamente o que precisamos para corrigir o motor.
- **Torneios da Limitless**: `python import_limitless.py list` e `python import_limitless.py import --latest 3`
  (precisa de internet; baixa o top 8 para `decks/limitless/`).

## 8. Problemas comuns

| Sintoma | Solução |
|---|---|
| `ModuleNotFoundError: No module named 'numpy'` | ambiente virtual não ativado (passo 3) ou `pip install numpy` |
| `ModuleNotFoundError: No module named 'ptcg'` | rode os comandos de dentro da pasta `poketrainer` |
| Acentos/símbolos estranhos no terminal do Windows | use o Windows Terminal, ou rode `chcp 65001` antes |
| Porta 8765 ocupada | `python server.py --port 9000` |
| `import_limitless.py` falha | sem internet ou a Limitless mudou o site: avise e envie a mensagem de erro |
