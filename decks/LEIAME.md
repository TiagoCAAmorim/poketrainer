# Decks

Arquivos de texto no formato de lista do Pokémon TCG Live (dá para importar direto no jogo).
Linhas iniciadas por `#` guardam informações extras (arquétipo, jogador, torneio, colocação…).

| Pasta | Conteúdo |
|---|---|
| `meus/` | decks criados por você (`gerenciar_decks.py criar/montar/copiar` ou pela interface) |
| `importados/` | listas importadas de arquivos (`gerenciar_decks.py importar`) |
| `limitless/<torneio>/` | top 8 de torneios Regionais/Internacionais/Mundial da Limitless (`import_limitless.py`) |
| `_lixeira/` | decks apagados (podem ser recuperados movendo o arquivo de volta) |

As listas aceitam nomes em inglês ou português, com ou sem coleção/número:
`4 Ultra Ball MEG 131`, `4 Ultra Bola`, `8 Energia de Fogo Básica`.
