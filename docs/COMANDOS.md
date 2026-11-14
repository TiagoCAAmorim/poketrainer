# Comandos de terminal

Tudo o que a interface faz também pode ser feito por linha de comando. Rode de dentro da pasta `poketrainer`,
com o ambiente virtual ativado (veja o [README](../README.md)). No Windows, use `py` se `python` não funcionar.

## Interface e imagens

```
python server.py [--port 9000] [--no-browser]     # http://localhost:8765
python baixar_imagens.py                          # imagens das cartas → imagens/ (fora do git); opções em CARTAS.md
```

## Biblioteca de cartas

```
python cartas.py buscar "Ultra Bola"       # nome em inglês ou português
python cartas.py mostrar TWM-130           # ficha completa (ataques, Habilidades, status no simulador)
python cartas.py listar | resumo           # resumo = cobertura de cartas
python cartas.py atualizar                 # regera cartas/cartas.db
```

## Decks (guia completo em [DECKS.md](../DECKS.md))

```
python gerenciar_decks.py listar
python gerenciar_decks.py criar meu_deck --arquivo lista.txt     # lista exportada do TCG Live ou da Limitless
python gerenciar_decks.py montar meu_deck                         # montagem interativa
python gerenciar_decks.py mostrar|editar|copiar|exportar|validar|apagar ...
python import_limitless.py list                                   # torneios disponíveis
python import_limitless.py import --latest 5                      # top 8 dos últimos torneios → decks/limitless/
python limpar_decks.py                                            # separa decks com cartas fora da rotação
```

## Logs

```
python gerenciar_logs.py importar partida.txt      # "Copy Log" do TCG Live → guardado e reproduzido
python gerenciar_logs.py listar | mostrar | rever | atividade | reprocessar
python replay_log.py tests/fixtures/ptcgl_logs/*.log
python gerenciar_logs.py problemas [abertos|corrigidos|todos]   # comentários feitos pelo botão 💬 Comentar
python gerenciar_logs.py problema <ID>
python gerenciar_logs.py corrigir <ID> --nota "o que mudou"
python gerenciar_logs.py fixar                                  # partidas boas da interface viram teste
```

## Simulação, teste e otimização de decks

```
python simulate.py meus/meu_deck 01_hedrick_dragapult --games 200 [--salvar-log] [--agent model:ias/nivel_9.pt]
python testar_deck.py <deck> [--contra filtro] [--maximo N] [--sugerir --salvar]   # 1 deck × toda a base (web /testar)
python optimize.py <deck> --gauntlet 01_hedrick_dragapult 05_heiremans_crustle
python melhorar_heuristica.py [--avaliar|--resetar]    # ajusta os pesos da IA heurística
```

## Impressão

```
python imprimir_cartas.py <deck> [--adicionar "2 Ultra Ball"] [--remover "1 Boss's Orders"] [--escala 90] [--papel A4|Office|A5|LxA] [--simplificado]
```
O PDF sai em `pdfs/`. Na impressora escolha "tamanho real / 100%", sem ajustar à página.

## IA (precisa do PyTorch)

```
python imitar.py gerar|treinar|avaliar        # pré-treino imitando a heurística
python train.py --resume checkpoints/imitacao.pt   # PPO (self-play)
python ia.py historico|acompanhar|niveis|nivel|elo|escada
```
Passo a passo, tempos e opções: [IA_TREINO.md](IA_TREINO.md). As redes dos níveis 4–9 ficam em `ias/` (versionadas no git).

## Reconstruir a base de cartas (quando sair coleção nova)

```
python tools/build_carddb.py        # clona pokemon-tcg-data e TCGdex em .cache/
python tools/build_pt_texts.py
python cartas.py atualizar
```
