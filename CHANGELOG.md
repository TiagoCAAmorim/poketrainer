# Changelog

Principais novidades de cada versão, da mais nova para a mais antiga.
As versões foram numeradas depois do fato, a partir do histórico do git (ainda não há *tags* nem *releases* no GitHub).

## [Não lançado]
- **Atualizar o programa pela interface**: a página inicial avisa "Nova versão disponível" e o botão *Atualizar agora* baixa o
  código, as redes novas de `ias/` e os dados oficiais, e reinicia o servidor. Funciona em clone (git, só na `main`) e em
  instalação por ZIP (nunca toca em `decks/meus`, `logs`, `imagens`, `pdfs`). Também por `python atualizar.py`.

## [0.4.0] — 2026-11-14 · Níveis de IA, impressão e teste de deck
- **IAs por nível de dificuldade (0–9)**: a heurística é o nível 0 e as redes treinadas ficam em `ias/`
  (níveis 4 a 9, ~4,6 MB cada). A interface lista "IA nível N". O nível 9 vence a heurística em 85% das partidas.
- **Testar um deck** (`/testar`, `testar_deck.py`): seu deck contra toda a base, com vitórias por ordem de jogo,
  cartas e combos mais úteis, vez em que saem os Prêmios, matchups difíceis e trocas de cartas sugeridas.
  Dá para escolher os decks oponentes e a IA, limitar as cartas candidatas às trocas, exportar PDF, **abortar** o teste
  a qualquer momento e acompanhar o andamento (partidas por segundo, tempo restante, log de cada etapa).
- **Imprimir cartas em PDF** (`/imprimir`, `imprimir_cartas.py`): escala em % do tamanho real, papel A4/Office/A5…
  e versão simplificada em preto e branco.

## [0.3.0] — 2026-11-13 a 14 · IA que aprende
- Pré-treino por **imitação da heurística** e **PPO** (self-play) com partidas em paralelo.
- Treinos longos: `ppo1` 73% → `ppo2` 80% → `ppo4` **85%** contra a heurística; platô superado com lotes grandes (`--games 960`).
- Confronto direto entre redes (`--oponente model:…`), varredura de hiperparâmetros e métricas no W&B.
- Guia de treino em outro computador. Bug do motor encontrado pelo treino (Night Joker copiando Night Joker) corrigido.
- Banner no README.

## [0.2.0] — 2026-10-18 · Cobertura total, interface e rulings
- **100% das cartas** do formato (2.083) com efeito implementado (451 cartas novas) e novos ganchos no motor.
- Dezenas de correções de regras conferidas com o Compendium do Pokégym (rulings de 2024 a 2026), cada uma com cenário de teste.
- Interface: imagens das cartas (`baixar_imagens.py`, com a Limitless como 3ª fonte e opção `--manual`), painel com a
  imagem da carta, controle de velocidade, montador de decks com imagens, página de cartas com filtros e detalhes.
- **Botão 💬 Comentar** para apontar erros durante a partida, aviso diário de pendências e partidas da interface viram teste.
- **Consultor de IA** (sugestões durante a partida) e correções na IA heurística (`melhorar_heuristica.py`).

## [0.1.0] — 2026-10-17 · Primeira versão
- Motor de regras do Pokémon TCG Live: preparação, turnos, dano, condições especiais, Prêmios e vitória, determinístico e reproduzível.
- Base com as cartas do Padrão TEF–30C em inglês e português; biblioteca `cartas/` e consulta por `cartas.py`.
- Decks: leitura de listas do TCG Live/Limitless, validação, gerenciador e importador do top 8 da Limitless; 12 decks de teste.
- Reprodução de logs "Copy Log" do TCG Live, conferindo dano e nocautes (4 logs de exemplo a 100%).
- LOG de atividade, partidas e simulações; interface local com página inicial e simulador.
