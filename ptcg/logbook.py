"""LOG do sistema: tudo o que acontece fica guardado na pasta logs/.

    logs/
      atividade.log                  linha legível por evento (decks criados, importações, simulações…)
      atividade.jsonl                o mesmo, com os dados completos (1 JSON por linha)
      partidas_tcglive/              logs copiados do Pokémon TCG Live ("Copy Log")
        AAAA-MM-DD_HHMMSS_<j1>_vs_<j2>.txt     texto original
        AAAA-MM-DD_HHMMSS_<j1>_vs_<j2>.json    resultado da reprodução no motor
        indice.jsonl
      simulacoes/<AAAA-MM-DD_HHMMSS>_<descricao>.jsonl   1 partida simulada por linha
      interface/partidas.jsonl       partidas jogadas na interface gráfica

Cada partida do motor é gravada com decks (ids), semente e a sequência de decisões (`history`):
isso basta para reproduzi-la exatamente (`gerenciar_logs.py rever …`).
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / 'logs'
_LOCK = threading.Lock()


def _now():
    return datetime.now()


def _stamp(dt=None):
    return (dt or _now()).strftime('%Y-%m-%d_%H%M%S')


def _slug(s, n=30):
    s = re.sub(r'[^\w\-]+', '_', str(s), flags=re.UNICODE).strip('_')
    return (s or 'x')[:n]


def _append(path: Path, line: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, open(path, 'a', encoding='utf-8') as f:
        f.write(line.rstrip('\n') + '\n')


def registrar(categoria: str, mensagem: str, **dados):
    """Registra um evento em logs/atividade.log (+ .jsonl com os dados)."""
    dt = _now()
    _append(LOG_DIR / 'atividade.log', f'{dt:%Y-%m-%d %H:%M:%S} [{categoria}] {mensagem}')
    _append(LOG_DIR / 'atividade.jsonl', json.dumps({'quando': dt.isoformat(timespec='seconds'),
                                                     'categoria': categoria, 'mensagem': mensagem,
                                                     **dados}, ensure_ascii=False, default=str))


# ------------------------------------------------------------------ partidas do motor
def partida_registro(g, **extra) -> dict:
    """Resumo reproduzível de uma partida (Game) do motor."""
    return {
        'quando': _now().isoformat(timespec='seconds'),
        'jogadores': list(g.names), 'decks_ids': g.deck_lists, 'semente': g.seed,
        'primeiro': g.first_player, 'vencedor': g.winner, 'motivo': g.end_reason, 'turnos': g.turn,
        'premios_pegos': [g.prizes_taken(0), g.prizes_taken(1)], 'decisoes': len(g.history),
        'history': list(g.history), **extra,
    }


class SessaoSimulacao:
    """Arquivo de log de uma rodada de simulações (simulate.py / optimize.py --salvar-log)."""

    def __init__(self, descricao: str, guardar_texto=False):
        self.path = LOG_DIR / 'simulacoes' / f'{_stamp()}_{_slug(descricao, 60)}.jsonl'
        self.guardar_texto = guardar_texto
        self.n = 0

    def gravar(self, g, **extra):
        rec = partida_registro(g, **extra)
        if self.guardar_texto:
            rec['log'] = [x['msg'] for x in g.log]
        _append(self.path, json.dumps(rec, ensure_ascii=False))
        self.n += 1

    def gravar_registro(self, rec: dict):
        _append(self.path, json.dumps(rec, ensure_ascii=False))
        self.n += 1


def salvar_partida_interface(g, decks=None, controles=None, comentarios=None):
    rec = partida_registro(g, decks=decks, controles=controles, log=[x['msg'] for x in g.log],
                           comentarios=comentarios or [])
    _append(LOG_DIR / 'interface' / 'partidas.jsonl', json.dumps(rec, ensure_ascii=False))
    registrar('interface', f'partida terminada: {g.names[0]} x {g.names[1]} — '
                           f'{"empate" if g.winner == -1 else g.names[g.winner] + " venceu"} ({g.end_reason})',
              decks=decks)


# ------------------------------------------------------------------ problemas apontados nas partidas
PROBLEMAS = LOG_DIR / 'problemas.jsonl'   # versionado: é a memória dos problemas (abertos e corrigidos)


def _problemas_todos() -> list:
    return _read_jsonl(PROBLEMAS)


def registrar_problema(g, texto: str, decks=None, controles=None) -> dict:
    """Guarda um comentário do usuário sobre a decisão atual da partida (status 'aberto').

    Inclui decks, semente e decisões até aqui, então `rever_partida(rec)` reproduz o momento exato.
    """
    pr = g.prompt
    rec = {
        'id': f'P{len(_problemas_todos()) + 1:03d}', 'status': 'aberto', 'texto': texto.strip(),
        'quando': _now().isoformat(timespec='seconds'),
        'decisao': len(g.history), 'turno': g.turn,
        'prompt': None if pr is None else {'jogador': pr.player, 'hint': pr.hint, 'texto': pr.text,
                                           'opcoes': [o.label for o in pr.options]},
        'ultimas_linhas': [x['msg'] for x in g.log[-12:]],
        'jogadores': list(g.names), 'decks': decks, 'controles': controles,
        'decks_ids': g.deck_lists, 'semente': g.seed, 'history': list(g.history),
    }
    _append(PROBLEMAS, json.dumps(rec, ensure_ascii=False))
    registrar('problema', f'{rec["id"]} (turno {g.turn}, decisão {rec["decisao"]}): {rec["texto"][:120]}')
    return rec


def problemas(status=None) -> list:
    return [r for r in _problemas_todos() if status is None or r['status'] == status]


def atualizar_problema(pid: str, status: str, nota='') -> dict:
    """Marca um problema como 'corrigido' (ou reabre). Reescreve o arquivo."""
    recs = _problemas_todos()
    alvo = next((r for r in recs if r['id'] == pid.upper()), None)
    if alvo is None:
        raise KeyError(f'problema {pid} não encontrado')
    alvo['status'] = status
    if status == 'corrigido':
        alvo['corrigido_em'] = _now().isoformat(timespec='seconds')
        alvo['correcao'] = nota
    else:
        alvo.pop('corrigido_em', None)
    with _LOCK:
        PROBLEMAS.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in recs), encoding='utf-8')
    registrar('problema', f'{alvo["id"]} → {status}' + (f': {nota}' if nota else ''))
    return alvo


def rever_partida(rec: dict):
    """Refaz uma partida gravada (mesmos decks, semente e decisões) e devolve o Game."""
    from .engine import Game
    g = Game(rec['decks_ids'][0], rec['decks_ids'][1], seed=rec['semente'], names=rec.get('jogadores') or
             ('Jogador 1', 'Jogador 2'))
    for i in rec['history']:
        if g.done:
            break
        g.step(i)
    return g


# ------------------------------------------------------------------ logs do Pokémon TCG Live
def salvar_log_tcglive(texto: str, relatorio=None, origem='manual') -> Path:
    """Guarda o texto do log e (se houver) o resultado da reprodução. Evita duplicatas pelo conteúdo."""
    import hashlib
    d = LOG_DIR / 'partidas_tcglive'
    d.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(texto.strip().encode('utf-8')).hexdigest()[:12]
    for line in _read_jsonl(d / 'indice.jsonl'):
        if line.get('hash') == h:
            p = d / line['arquivo']
            if relatorio is not None:
                _write_report(p.with_suffix('.json'), relatorio, h)
            return p
    players = []
    try:
        from .replay.parse import parse_log
        players = parse_log(texto).players[:2]
    except Exception:
        pass
    name = f'{_stamp()}_{_slug(players[0] if players else "j1", 20)}_vs_{_slug(players[1] if len(players) > 1 else "j2", 20)}'
    p = d / f'{name}.txt'
    p.write_text(texto, encoding='utf-8')
    info = {'arquivo': p.name, 'hash': h, 'jogadores': players, 'importado_em': _now().isoformat(timespec='seconds'),
            'origem': origem}
    if relatorio is not None:
        info.update(_write_report(p.with_suffix('.json'), relatorio, h))
    _append(d / 'indice.jsonl', json.dumps(info, ensure_ascii=False))
    registrar('tcglive', f'log guardado: {p.name}', jogadores=players, origem=origem)
    return p


def _write_report(path: Path, rep, h):
    info = {'acoes': [rep.actions_done, rep.actions_total], 'turnos': [rep.turns_done, rep.turns_total],
            'completo': bool(rep.finished and not rep.divergence), 'divergencia': rep.divergence,
            'danos_conferidos': [list(x) for x in rep.damage_checks], 'notas': rep.notes, 'hash': h,
            'resumo': rep.summary()}
    path.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding='utf-8')
    return {'completo': info['completo'], 'acoes': info['acoes']}


def _read_jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def ler_jsonl(path) -> list:
    return _read_jsonl(Path(path))


def logs_tcglive() -> list:
    return _read_jsonl(LOG_DIR / 'partidas_tcglive' / 'indice.jsonl')


def sessoes_simulacao() -> list:
    d = LOG_DIR / 'simulacoes'
    return sorted(d.glob('*.jsonl')) if d.exists() else []


class Cronometro:
    def __init__(self):
        self.t = time.time()

    def __call__(self):
        return round(time.time() - self.t, 1)
