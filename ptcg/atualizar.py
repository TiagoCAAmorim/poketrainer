"""Atualização do programa pela interface (e por `python atualizar.py`).

Dois modos, detectados sozinhos:
  * **git**  — a pasta é um clone (`.git/`) e o `git` existe: `git fetch` + `git pull --ff-only` do repositório público (HTTPS,
    sem precisar de chave SSH). Só atualiza na branch `main`; outra branch é trabalho de desenvolvimento e fica intocada.
  * **zip**  — instalação por ZIP: baixa o ZIP da `main` no GitHub e sobrescreve só o código, as redes (`ias/`) e os dados
    oficiais; nunca mexe nos seus decks, logs, imagens, PDFs ou treinos (ver `PROTEGIDOS`). A versão instalada fica em
    `.versao_instalada` (SHA do commit + lista de arquivos, para apagar o que saiu do projeto).

Nada aqui exige conta no GitHub: usa só a API pública de leitura e o ZIP da branch.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REPO = 'TiagoCAAmorim/poketrainer'
BRANCH = 'main'
REPO_URL = f'https://github.com/{REPO}.git'
ZIP_URL = f'https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip'
API_URL = f'https://api.github.com/repos/{REPO}/commits/{BRANCH}'
MARCA = '.versao_instalada'
TIMEOUT = 20

# Caminhos (prefixos relativos à raiz) que a atualização por ZIP nunca sobrescreve nem apaga: dados do usuário e gerados.
PROTEGIDOS = (
    '.git/', '.cache/', MARCA, 'decks/meus/', 'decks/limitless/', 'decks/importados/', 'decks/_lixeira/',
    'decks/_fora_da_rotacao/', 'logs/', 'imagens/', 'pdfs/', 'dados/', 'checkpoints/', 'wandb/', 'cartas/cartas.db',
    '__pycache__/', 'venv/', '.venv/',
)


class ErroAtualizacao(Exception):
    pass


def _protegido(rel: str) -> bool:
    rel = rel.replace('\\', '/')
    return any(rel == p.rstrip('/') or rel.startswith(p) for p in PROTEGIDOS) or '/__pycache__/' in rel


# ----------------------------------------------------------------------------- git
def _git(*args, raiz: Path | None = None, timeout=TIMEOUT) -> str:
    try:
        r = subprocess.run(['git', *args], cwd=raiz or RAIZ, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    except FileNotFoundError:
        raise ErroAtualizacao('git não encontrado')
    except subprocess.TimeoutExpired:
        raise ErroAtualizacao('sem resposta do GitHub (tempo esgotado); confira a internet')
    if r.returncode != 0:
        if 'could not read Username' in r.stderr or 'not found' in r.stderr.lower():
            raise ErroAtualizacao('repositório inacessível no GitHub (ainda privado ou sem internet)')
        raise ErroAtualizacao((r.stderr or r.stdout).strip() or f'git {args[0]} falhou')
    return r.stdout.strip()


def modo(raiz: Path | None = None) -> str:
    raiz = raiz or RAIZ
    if (raiz / '.git').exists() and shutil.which('git'):
        return 'git'
    return 'zip'


def _http(url: str, accept: str | None = None) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': 'ptcg-lab-atualizador', **({'Accept': accept} if accept else {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read()
    except Exception as e:
        raise ErroAtualizacao(f'não consegui acessar o GitHub ({e}); confira a internet')


def _sha_remoto() -> dict:
    d = json.loads(_http(API_URL, 'application/vnd.github+json'))
    c = d['commit']
    return {'sha': d['sha'], 'mensagem': c['message'].splitlines()[0], 'data': (c['committer'] or {}).get('date', '')[:10]}


def versao_local(raiz: Path | None = None) -> dict:
    raiz = raiz or RAIZ
    if modo(raiz) == 'git':
        try:
            return {'sha': _git('rev-parse', 'HEAD', raiz=raiz), 'branch': _git('rev-parse', '--abbrev-ref', 'HEAD', raiz=raiz),
                    'data': _git('log', '-1', '--format=%cs', raiz=raiz)}
        except ErroAtualizacao:
            return {'sha': None}
    f = raiz / MARCA
    if f.exists():
        try:
            return {'sha': json.loads(f.read_text(encoding='utf-8')).get('sha')}
        except Exception:
            pass
    return {'sha': None}


# ----------------------------------------------------------------------------- verificar
def verificar(raiz: Path | None = None, repo_url: str | None = None) -> dict:
    """Devolve {'modo','local','remoto','disponivel','novidades':[...],'pode_atualizar','aviso'}. Levanta ErroAtualizacao sem rede."""
    raiz = raiz or RAIZ
    repo_url = repo_url or REPO_URL
    m = modo(raiz)
    loc = versao_local(raiz)
    out = {'modo': m, 'local': loc, 'remoto': None, 'disponivel': False, 'novidades': [], 'pode_atualizar': True, 'aviso': ''}
    if m == 'git':
        if loc.get('branch') != BRANCH:
            out['pode_atualizar'] = False
            out['aviso'] = f"Você está na branch '{loc.get('branch')}' (desenvolvimento): a atualização automática só vale na '{BRANCH}'."
        _git('fetch', '--quiet', repo_url, BRANCH, raiz=raiz, timeout=60)
        novo = _git('rev-parse', 'FETCH_HEAD', raiz=raiz)
        out['remoto'] = {'sha': novo}
        try:
            _git('merge-base', '--is-ancestor', novo, 'HEAD', raiz=raiz)    # remoto já está no meu histórico
            return out
        except ErroAtualizacao:
            pass
        out['disponivel'] = True
        out['novidades'] = _git('log', '--format=%cs  %s', '-n', '15', 'HEAD..FETCH_HEAD', raiz=raiz).splitlines()
        return out
    r = _sha_remoto()
    out['remoto'] = r
    out['disponivel'] = loc.get('sha') != r['sha']
    if out['disponivel']:
        out['novidades'] = [f"{r['data']}  {r['mensagem']}"]
        if loc.get('sha') is None:
            out['aviso'] = 'Versão instalada desconhecida (primeira atualização por ZIP): vale atualizar uma vez para registrá-la.'
    return out


# ----------------------------------------------------------------------------- aplicar
def _aplicar_git(raiz: Path, repo_url: str) -> str:
    if _git('rev-parse', '--abbrev-ref', 'HEAD', raiz=raiz) != BRANCH:
        raise ErroAtualizacao(f"a branch atual não é '{BRANCH}'; atualização automática desligada")
    antes = _git('rev-parse', 'HEAD', raiz=raiz)
    try:
        _git('pull', '--ff-only', '--quiet', repo_url, BRANCH, raiz=raiz, timeout=300)
    except ErroAtualizacao as e:
        raise ErroAtualizacao('não foi possível atualizar sem perder alterações suas nos arquivos do programa '
                              f'(desfaça-as ou use `git stash`).\nDetalhe: {e}')
    depois = _git('rev-parse', 'HEAD', raiz=raiz)
    return f'{antes[:7]} → {depois[:7]}'


def _aplicar_zip(raiz: Path, zip_url: str, sha: str | None) -> str:
    antigos: set[str] = set()
    f = raiz / MARCA
    if f.exists():
        try:
            antigos = set(json.loads(f.read_text(encoding='utf-8')).get('arquivos', []))
        except Exception:
            pass
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / 'novo.zip'
        zpath.write_bytes(_http(zip_url))
        try:
            z = zipfile.ZipFile(zpath)
        except zipfile.BadZipFile:
            raise ErroAtualizacao('o arquivo baixado não é um ZIP válido')
        novos: list[str] = []
        with z:
            membros = [i for i in z.infolist() if not i.is_dir()]
            for i in membros:                                   # valida tudo antes de escrever qualquer coisa
                rel = i.filename.split('/', 1)[1] if '/' in i.filename else ''
                if rel and (rel.startswith('/') or '..' in rel.split('/')):
                    raise ErroAtualizacao(f'caminho suspeito no ZIP: {i.filename}')
            n = 0
            for i in membros:
                rel = i.filename.split('/', 1)[1] if '/' in i.filename else ''
                if not rel or _protegido(rel):
                    continue
                novos.append(rel)
                dest = raiz / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmpf = dest.with_name(dest.name + '.novo')
                with z.open(i) as src, open(tmpf, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                os.replace(tmpf, dest)
                n += 1
    for rel in antigos - set(novos):                            # arquivos que saíram do projeto
        if not _protegido(rel) and (raiz / rel).is_file():
            try:
                (raiz / rel).unlink()
            except OSError:
                pass
    f.write_text(json.dumps({'sha': sha, 'quando': time.strftime('%Y-%m-%d %H:%M:%S'), 'arquivos': sorted(novos)}), encoding='utf-8')
    return f'{n} arquivos atualizados'


def aplicar(raiz: Path | None = None, repo_url: str | None = None, zip_url: str | None = None) -> dict:
    """Atualiza e devolve {'ok': True, 'resumo', 'reiniciar': True, 'dependencias': bool}. Levanta ErroAtualizacao."""
    raiz = raiz or RAIZ
    req_antes = (raiz / 'requirements.txt').read_bytes() if (raiz / 'requirements.txt').exists() else b''
    if modo(raiz) == 'git':
        resumo = _aplicar_git(raiz, repo_url or REPO_URL)
    else:
        try:
            sha = _sha_remoto()['sha']
        except ErroAtualizacao:
            sha = None
        resumo = _aplicar_zip(raiz, zip_url or ZIP_URL, sha)
    req_depois = (raiz / 'requirements.txt').read_bytes() if (raiz / 'requirements.txt').exists() else b''
    return {'ok': True, 'resumo': resumo, 'reiniciar': True, 'dependencias': req_antes != req_depois}


def pip_install(raiz: Path | None = None) -> str:
    """Instala requirements.txt (usado quando ele mudou na atualização)."""
    import sys
    raiz = raiz or RAIZ
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-r', 'requirements.txt'], cwd=raiz,
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise ErroAtualizacao('falha ao instalar dependências:\n' + (r.stderr or r.stdout)[-600:])
    return 'dependências atualizadas'
