# LOG

Tudo o que o sistema faz fica registrado aqui.

| Arquivo / pasta | Conteúdo |
|---|---|
| `atividade.log` | uma linha legível por evento (deck criado/editado/importado, torneio baixado da Limitless, simulação, log do TCG Live importado, partida jogada na interface) |
| `atividade.jsonl` | os mesmos eventos com todos os dados (1 JSON por linha) |
| `partidas_tcglive/` | logs copiados do Pokémon TCG Live (`.txt` original) + resultado da reprodução no motor (`.json`) + `indice.jsonl` |
| `simulacoes/` | partidas simuladas (`simulate.py --salvar-log`), 1 partida por linha, com decks, semente e todas as decisões — dá para rever qualquer uma exatamente |
| `problemas.jsonl` | comentários feitos pelo usuário nas partidas (botão 💬 Comentar), com status aberto/corrigido e a partida até aquele ponto (**versionado**) |
| `interface/partidas.jsonl` | partidas jogadas na interface gráfica |
| `ia/treinos.jsonl` | treinos e avaliações da IA (dados gerados, imitação, avaliações, início/avaliações/fim do PPO) — `python ia.py historico` (**versionado**) |

```
python gerenciar_logs.py importar minha_partida.txt     # guarda e reproduz um log do TCG Live
python gerenciar_logs.py listar
python gerenciar_logs.py mostrar <nome>
python gerenciar_logs.py rever logs/simulacoes/<arquivo>.jsonl --partida 3
python gerenciar_logs.py atividade --ultimos 30
python gerenciar_logs.py imitacao dados/imitacao.pkl    # dados de treino (imitação) a partir dos logs
```

```
python gerenciar_logs.py problemas [abertos|corrigidos|todos]
python gerenciar_logs.py problema P003
python gerenciar_logs.py corrigir P003 --nota "o que foi feito"
python gerenciar_logs.py fixar     # partidas sem comentários → tests/fixtures/partidas/ (teste do motor)
```
