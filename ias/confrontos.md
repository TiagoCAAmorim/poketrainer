# Confrontos entre os níveis da IA

Gerado por `python ia.py niveis` a partir de `logs/ia/treinos.jsonl` (não editar à mão).
Vitórias do nível mais alto (empate = ½), erro padrão ≈ 0,5/√partidas.

| nível | nome | Elo | origem |
|---:|---|---:|---|
| 0 | heurística | 0 | `heuristic` |
| 4 | ppo1 | 175 | `checkpoints/ppo1/latest.pt` |
| 5 | sweep-g480 | 215 | `checkpoints/sweep1/g480/latest.pt` |
| 6 | ppo2 | 236 | `checkpoints/ppo2/latest.pt` |
| 7 | lote960 | 282 | `checkpoints/plato/lote960/latest.pt` |
| 8 | ppo4-t2 | 305 | `checkpoints/ppo4/t2/latest.pt` |
| 9 | ppo4-t3 | 311 | `checkpoints/ppo4/t3/latest.pt` |

| alto × baixo | vitórias do alto | partidas | esperado pelo Elo |
|---|---:|---:|---:|
| 9 × 8 | 51.9% | 1000 | 50.9% |
| 9 × 6 | 60.9% | 1000 | 60.6% |
| 9 × 0 | 85.1% | 2000 | 85.7% |
| 8 × 6 | 60.0% | 1000 | 59.7% |
| 8 × 4 | 69.1% | 1000 | 67.9% |
| 8 × 0 | 85.0% | 2000 | 85.3% |
| 7 × 0 | 84.8% | 1000 | 83.6% |
| 6 × 4 | 58.7% | 1000 | 58.7% |
| 6 × 0 | 79.7% | 2000 | 79.6% |
| 5 × 0 | 77.5% | 2000 | 77.5% |
| 4 × 0 | 73.7% | 3000 | 73.2% |
