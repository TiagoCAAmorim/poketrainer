"""Níveis de dificuldade da IA: 0 = heurística … 9 = melhor rede treinada até agora.

As redes escolhidas ficam em `ias/` (versionadas, pesos em float16, ~4,6 MB cada) para não se perderem quando
`checkpoints/` (fora do git) for limpo ou a máquina mudar. Cada rede é salva com o próprio nome
(`ias/<nome>.pt`): ao trocar a rede de um nível, a anterior continua em `ias/` (fora da escala, mas guardada). `ias/niveis.json` descreve cada nível:

    {"nivel": 4, "nome": "ppo1", "arquivo": "ias/ppo1.pt", "origem": "checkpoints/ppo1/latest.pt",
     "elo": 178, "vs_heuristica": 0.739, "descricao": "..."}

Critério de dificuldade: **Elo relativo à heurística** (heurística = 0), ajustado por máxima verossimilhança
(Bradley–Terry) a TODAS as avaliações registradas em logs/ia/treinos.jsonl — contra a heurística e confrontos
diretos entre redes. +100 de Elo ≈ vence 64% das partidas contra quem está 100 abaixo; +200 ≈ 76%; +300 ≈ 85%.
Os níveis devem subir de Elo e, de preferência, cada um vencer o anterior em confronto direto (`python ia.py escada`).

Uso: `make_agent('nivel:7')`, `python ia.py niveis`, `python ia.py nivel 9 checkpoints/.../latest.pt --nome ...`.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / 'ias'
ARQ = DIR / 'niveis.json'
FAIXAS = [(0, 2, 'fácil'), (3, 5, 'médio'), (6, 7, 'difícil'), (8, 9, 'muito difícil')]
HEURISTICA = {'nivel': 0, 'nome': 'heurística', 'arquivo': None, 'origem': 'heuristic', 'elo': 0,
              'vs_heuristica': 0.5, 'descricao': 'Regras escritas à mão (ptcg/agents.py); a referência do Elo.'}


def faixa(nivel: int) -> str:
    return next((f for a, b, f in FAIXAS if a <= nivel <= b), '?')


def carregar() -> list[dict]:
    """Lista de níveis (sempre inclui o 0 = heurística), ordenada."""
    niveis = json.loads(ARQ.read_text()) if ARQ.exists() else []
    if not any(n['nivel'] == 0 for n in niveis):
        niveis.append(dict(HEURISTICA))
    return sorted(niveis, key=lambda n: n['nivel'])


def salvar(niveis: list[dict]):
    DIR.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(sorted(niveis, key=lambda n: n['nivel']), ensure_ascii=False, indent=1) + '\n')


def obter(nivel: int) -> dict:
    for n in carregar():
        if n['nivel'] == int(nivel):
            return n
    raise KeyError(f'nível {nivel} não existe (disponíveis: {[n["nivel"] for n in carregar()]})')


def spec(nivel: int) -> str:
    """Especificação de agente (make_agent) do nível: 'heuristic' ou 'model:<raiz>/ias/<nome>.pt'."""
    n = obter(nivel)
    return f"model:{ROOT / n['arquivo']}" if n.get('arquivo') else 'heuristic'


def rotulo(n: dict) -> str:
    elo = n.get('elo')
    s = f"IA nível {n['nivel']} · {faixa(n['nivel'])} — {n['nome']}"
    return s + (f" (Elo {elo:+d})" if elo is not None else '')


def exportar(checkpoint: str, destino: Path):
    """Cópia compacta do checkpoint (só pesos em float16 + config); load_checkpoint lê normalmente."""
    import torch
    ck = torch.load(checkpoint, map_location='cpu', weights_only=False)
    estado = {k: (v.half() if v.is_floating_point() else v) for k, v in ck['model'].items()}
    extra = {k: v for k, v in (ck.get('extra') or {}).items() if isinstance(v, (int, float, str, bool))}
    extra['origem'] = str(checkpoint)
    destino.parent.mkdir(parents=True, exist_ok=True)
    torch.save({'model': estado, 'config': ck['config'], 'extra': extra}, destino)


def _antigas() -> list[dict]:
    a = DIR / 'antigas.json'
    return json.loads(a.read_text()) if a.exists() else []


def definir(nivel: int, checkpoint: str, nome: str, descricao: str = ''):
    """Exporta `checkpoint` para ias/<nome>.pt e grava o nível (Elo e vitórias vêm de recalcular()).

    A rede que sai da escala continua em ias/ e vai para ias/antigas.json (com os nomes com que já foi avaliada);
    uma rede que só muda de nível leva junto o histórico de nomes."""
    if int(nivel) == 0:
        raise ValueError('o nível 0 é sempre a heurística')
    destino = DIR / f'{re.sub(r"[^A-Za-z0-9_.-]+", "_", nome)}.pt'
    exportar(checkpoint, destino)
    arq = str(destino.relative_to(ROOT))
    atuais, antigas = carregar(), _antigas()
    nomes_antigos = sorted({a for n in atuais + antigas if n.get('origem') == str(checkpoint)
                            for a in [n.get('arquivo')] + n.get('nomes_antigos', []) if a and a != arq})
    sai = [n for n in atuais if n['nivel'] == int(nivel) and n.get('arquivo')]
    niveis = [n for n in atuais if n['nivel'] != int(nivel)]
    niveis.append({'nivel': int(nivel), 'nome': nome, 'arquivo': arq, 'origem': str(checkpoint),
                   'descricao': descricao, **({'nomes_antigos': nomes_antigos} if nomes_antigos else {})})
    antigas += [{k: v for k, v in n.items() if k != 'nivel'} | {'ex_nivel': n['nivel']} for n in sai]
    em_uso = {n.get('origem') for n in niveis}
    vistos, limpas = set(), []
    for a in reversed(antigas):          # sem duplicatas e sem as que voltaram para a escala
        if a['origem'] not in em_uso and a['origem'] not in vistos:
            vistos.add(a['origem'])
            limpas.append(a)
    (DIR / 'antigas.json').write_text(json.dumps(limpas[::-1], ensure_ascii=False, indent=1) + '\n')
    salvar(niveis)
    return recalcular()


# ------------------------------------------------------------------ Elo (Bradley–Terry)
def _nome(x: str, apelidos: dict) -> str:
    x = x[6:] if x.startswith('model:') else x
    return apelidos.get(x, x)


def confrontos(registros=None) -> list[tuple[str, str, float, int]]:
    """(a, b, fração de vitórias de a, partidas) de todas as avaliações registradas. Redes de ias/ são
    identificadas com o checkpoint de origem; 'heuristic' é a âncora."""
    from ..logbook import treinos
    apelidos = {}
    for n in carregar():                 # nomes com que a rede já foi avaliada → checkpoint de origem
        for a in [n.get('arquivo')] + n.get('nomes_antigos', []):
            if a:
                apelidos[a] = n['origem']
    for r in _antigas():
        for a in [r['arquivo']] + r.get('nomes_antigos', []):
            apelidos[a] = r['origem']
    out = []
    for r in registros if registros is not None else treinos():
        if r.get('tipo') == 'avaliacao' and r.get('oponente') not in (None, 'random'):
            out.append((_nome(r['checkpoint'], apelidos), _nome(r['oponente'], apelidos),
                        float(r['vitorias']), int(r['partidas'])))
    return out


def elo(registros=None, ancora='heuristic', iteracoes=3000) -> dict[str, float]:
    """Elo de cada participante (âncora = 0) por máxima verossimilhança; empates contam ½ (já em 'vitorias')."""
    jogos = confrontos(registros)
    nomes = sorted({x for a, b, _, _ in jogos for x in (a, b)})
    if ancora not in nomes:
        return {}
    r = {n: 0.0 for n in nomes}
    k = math.log(10) / 400
    for _ in range(iteracoes):           # subida de gradiente na log-verossimilhança (convexa)
        g = {n: 0.0 for n in nomes}
        h = {n: 1e-9 for n in nomes}
        for a, b, w, n in jogos:
            p = 1 / (1 + math.exp(-k * (r[a] - r[b])))
            g[a] += n * (w - p)
            g[b] -= n * (w - p)
            h[a] += n * p * (1 - p) * k
            h[b] += n * p * (1 - p) * k
        mx = 0.0
        for n in nomes:
            if n != ancora:
                passo = g[n] / h[n]
                r[n] += max(-50.0, min(50.0, passo))
                mx = max(mx, abs(passo))
        if mx < 1e-4:
            break
    return {n: round(v - r[ancora], 1) for n, v in r.items()}


def recalcular() -> list[dict]:
    """Atualiza Elo e vitórias contra a heurística de cada nível a partir de logs/ia/treinos.jsonl."""
    ratings = elo()
    jogos = confrontos()
    niveis = carregar()
    for n in niveis:
        if n['nivel'] == 0:
            continue
        if n['origem'] in ratings:
            n['elo'] = int(round(ratings[n['origem']]))
        vs = [(w, p) for a, b, w, p in jogos if a == n['origem'] and b == 'heuristic']
        if vs:
            n['vs_heuristica'] = round(sum(w * p for w, p in vs) / sum(p for _, p in vs), 3)
            n['partidas_vs_heuristica'] = sum(p for _, p in vs)
    salvar(niveis)
    _salvar_confrontos(niveis, jogos, ratings)
    return niveis


def _salvar_confrontos(niveis, jogos, ratings):
    """ias/confrontos.md: avaliações (de logs/ia/treinos.jsonl) entre níveis e contra a heurística, para revisar
    a classificação quando entrar uma rede nova. O Elo usa TODAS as avaliações; esta tabela mostra as dos níveis."""
    por_origem = {n['origem']: n for n in niveis}
    agreg = {}
    for a, b, w, p in jogos:
        if a in por_origem and b in por_origem:
            na, nb = por_origem[a]['nivel'], por_origem[b]['nivel']
            if na < nb:
                na, nb, w = nb, na, 1 - w
            t = agreg.setdefault((na, nb), [0.0, 0])
            t[0] += w * p
            t[1] += p
    lin = ['# Confrontos entre os níveis da IA', '',
           'Gerado por `python ia.py niveis` a partir de `logs/ia/treinos.jsonl` (não editar à mão).',
           'Vitórias do nível mais alto (empate = ½), erro padrão ≈ 0,5/√partidas.', '',
           '| nível | nome | Elo | origem |', '|---:|---|---:|---|']
    lin += [f"| {n['nivel']} | {n['nome']} | {n.get('elo', '')} | `{n['origem']}` |" for n in niveis]
    lin += ['', '| alto × baixo | vitórias do alto | partidas | esperado pelo Elo |', '|---|---:|---:|---:|']
    nomes = {n['nivel']: n for n in niveis}
    for (na, nb), (s, p) in sorted(agreg.items(), reverse=True):
        da = ratings.get(nomes[na]['origem'], 0) - ratings.get(nomes[nb]['origem'], 0)
        esp = 1 / (1 + 10 ** (-da / 400))
        lin.append(f'| {na} × {nb} | {s / p:.1%} | {p} | {esp:.1%} |')
    (DIR / 'confrontos.md').write_text('\n'.join(lin) + '\n')
