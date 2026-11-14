# Confrontos entre os níveis da IA

Gerado por `python ia.py niveis` a partir de `logs/ia/treinos.jsonl` (não editar à mão).
Vitórias do nível mais alto (empate = ½), erro padrão ≈ 0,5/√partidas.

| nível | nome | Elo | origem |
|---:|---|---:|---|
| 0 | heurística | 0 | `heuristic` |
| 1 | faceis-f1 | 50 | `checkpoints/faceis/f1/latest.pt` |
| 2 | faceis-f2 | 100 | `checkpoints/faceis/f2/latest.pt` |
| 3 | faceis-f3 | 134 | `checkpoints/faceis/f3b/latest.pt` |
| 4 | ppo1 | 181 | `checkpoints/ppo1/latest.pt` |
| 5 | sweep-g480 | 205 | `checkpoints/sweep1/g480/latest.pt` |
| 6 | ppo2 | 240 | `checkpoints/ppo2/latest.pt` |
| 7 | lote960 | 277 | `checkpoints/plato/lote960/latest.pt` |
| 8 | ppo4-t3 | 308 | `checkpoints/ppo4/t3/latest.pt` |
| 9 | ppo6-lrdec | 358 | `checkpoints/ppo6/lrdec/latest.pt` |

| alto × baixo | vitórias do alto | partidas | esperado pelo Elo |
|---|---:|---:|---:|
| 9 × 8 | 56.8% | 1000 | 57.1% |
| 9 × 0 | 87.6% | 2000 | 88.7% |
| 8 × 6 | 60.9% | 1000 | 59.6% |
| 8 × 0 | 85.1% | 2000 | 85.5% |
| 7 × 6 | 54.1% | 1000 | 55.3% |
| 7 × 0 | 84.8% | 1000 | 83.1% |
| 6 × 5 | 57.2% | 1000 | 55.1% |
| 6 × 4 | 58.7% | 1000 | 58.5% |
| 6 × 0 | 79.7% | 2000 | 79.9% |
| 5 × 4 | 53.5% | 1000 | 53.4% |
| 5 × 0 | 77.5% | 2000 | 76.5% |
| 4 × 3 | 60.1% | 1000 | 56.7% |
| 4 × 0 | 73.7% | 3000 | 73.9% |
| 3 × 2 | 55.0% | 1000 | 55.0% |
| 3 × 0 | 70.1% | 2000 | 68.4% |
| 2 × 1 | 55.2% | 1000 | 57.0% |
| 2 × 0 | 64.9% | 2000 | 64.0% |
| 1 × 0 | 56.6% | 3000 | 57.2% |
