"""Instalador do PTCG Lab (só biblioteca padrão do Python; pensado para Windows, funciona também em Linux/macOS).

Instalação nova (precisa só do Python 3.10+; sem Git). Numa pasta qualquer, no terminal:

    python -c "import urllib.request as u; exec(u.urlopen('https://raw.githubusercontent.com/TiagoCAAmorim/poketrainer/main/instalar.py').read())"

Isso baixa o programa para a subpasta `poketrainer/`, cria o ambiente virtual (`.venv`), instala as dependências
(PyTorch só CPU), cria o atalho "PTCG Lab" na área de trabalho (Windows) e baixa as imagens das cartas.

Com o programa já baixado (ZIP ou Git), dentro da pasta dele:  python instalar.py
Opções: --gpu (PyTorch com CUDA + ferramentas de teste = requirements-dev.txt)  --sem-imagens (não baixar as figuras)  --sem-atalho
"""
from __future__ import annotations   # o aviso de "Python antigo" abaixo precisa aparecer mesmo no 3.9

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = 'TiagoCAAmorim/poketrainer'
ZIP_URL = f'https://github.com/{REPO}/archive/refs/heads/main.zip'
API_URL = f'https://api.github.com/repos/{REPO}/commits/main'
MARCA = '.versao_instalada'          # mesmo formato de ptcg/atualizar.py (permite atualizar depois pela interface)
NOME_ATALHO = 'PTCG Lab'


def falhar(msg: str):
    print(f'\n✗ {msg}')
    if os.name == 'nt' and sys.stdin and sys.stdin.isatty():
        input('Aperte Enter para fechar.')
    sys.exit(1)


def baixar(url: str) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': 'ptcg-lab-instalador'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except Exception as e:
        falhar(f'não consegui baixar {url}\n  ({e})\n  Confira a conexão com a internet e tente de novo.')


def baixar_programa(destino: Path) -> None:
    """Baixa o ZIP da `main` e extrai em `destino` (sem Git)."""
    print('• Baixando o programa (alguns MB)...')
    dados = baixar(ZIP_URL)
    try:
        sha = json.loads(baixar(API_URL))['sha']
    except Exception:
        sha = None
    with tempfile.TemporaryDirectory() as tmp:
        zp = Path(tmp) / 'p.zip'
        zp.write_bytes(dados)
        z = zipfile.ZipFile(zp)
        arquivos = []
        with z:
            for i in z.infolist():
                rel = i.filename.split('/', 1)[1] if '/' in i.filename else ''
                if i.is_dir() or not rel:
                    continue
                if rel.startswith('/') or '..' in rel.split('/'):
                    falhar(f'caminho suspeito no ZIP: {i.filename}')
                dest = destino / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(i) as src, open(dest, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                arquivos.append(rel)
    (destino / MARCA).write_text(json.dumps({'sha': sha, 'quando': time.strftime('%Y-%m-%d %H:%M:%S'),
                                             'arquivos': sorted(arquivos)}), encoding='utf-8')
    print(f'  {len(arquivos)} arquivos em {destino}')


def venv_python(raiz: Path) -> Path:
    return raiz / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def criar_venv_e_dependencias(raiz: Path, gpu: bool) -> Path:
    py = venv_python(raiz)
    if not py.exists():
        print('• Criando o ambiente virtual (.venv)...')
        if subprocess.run([sys.executable, '-m', 'venv', str(raiz / '.venv')]).returncode != 0:
            falhar('não consegui criar o ambiente virtual. No Linux instale o pacote python3-venv.')
    req = 'requirements-dev.txt' if gpu else 'requirements.txt'
    print(f'• Instalando dependências ({req}; o PyTorch é grande, pode levar alguns minutos)...')
    subprocess.run([str(py), '-m', 'pip', 'install', '-q', '--upgrade', 'pip'])
    if subprocess.run([str(py), '-m', 'pip', 'install', '-r', req], cwd=raiz).returncode != 0:
        falhar('a instalação das dependências falhou (veja as mensagens acima). Depois de resolver, rode de novo: python instalar.py')
    return py


def criar_lancador(raiz: Path) -> Path | None:
    """Arquivo que ativa o venv e abre a interface: .bat no Windows, .sh nos demais."""
    if os.name == 'nt':
        f = raiz / 'Iniciar PTCG Lab.bat'
        f.write_text('@echo off\r\ncd /d "%~dp0"\r\ntitle PTCG Lab\r\n'
                     'echo PTCG Lab: o navegador abre sozinho. Feche esta janela (ou Ctrl+C) para encerrar.\r\n'
                     '".venv\\Scripts\\python.exe" server.py\r\n'
                     'if errorlevel 1 pause\r\n', encoding='utf-8')
    else:
        f = raiz / 'iniciar.sh'
        f.write_text('#!/bin/sh\ncd "$(dirname "$0")"\nexec .venv/bin/python server.py\n', encoding='utf-8')
        f.chmod(0o755)
    return f


def criar_atalho_desktop(lancador: Path, raiz: Path) -> None:
    if os.name != 'nt':
        return
    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d '%s.lnk'));"
        "$s.TargetPath='%s';$s.WorkingDirectory='%s';$s.Description='Abre o PTCG Lab no navegador';"
        "$s.IconLocation='%s,0';$s.Save();Write-Output (Join-Path $d '%s.lnk')"
    ) % (NOME_ATALHO, str(lancador).replace("'", "''"), str(raiz).replace("'", "''"),
         str(venv_python(raiz)).replace("'", "''"), NOME_ATALHO)
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True)
    if r.returncode == 0:
        print(f'• Atalho criado na área de trabalho: {r.stdout.strip()}')
    else:
        print(f'! Não consegui criar o atalho ({r.stderr.strip()[:200]}). Use o arquivo "{lancador.name}" da pasta do programa.')


def instalar(raiz: Path, args: list[str]) -> None:
    if sys.version_info < (3, 10):
        falhar(f'Python {sys.version.split()[0]} é antigo: precisa do 3.10 ou mais novo (python.org/downloads).')
    py = criar_venv_e_dependencias(raiz, gpu='--gpu' in args)
    lanc = criar_lancador(raiz)
    if '--sem-atalho' not in args and lanc:
        criar_atalho_desktop(lanc, raiz)
    if '--sem-imagens' not in args:
        print('• Baixando as imagens das cartas (~190 MB, alguns minutos; pode interromper com Ctrl+C e retomar depois com: python baixar_imagens.py)...')
        try:
            subprocess.run([str(py), 'baixar_imagens.py'], cwd=raiz)
        except KeyboardInterrupt:
            print('\n! Download das imagens interrompido; para continuar depois: python baixar_imagens.py')
    print('\n✓ Pronto! Para usar, abra o atalho "%s" na área de trabalho' % NOME_ATALHO if os.name == 'nt' else '\n✓ Pronto!')
    print(f'  (ou rode "{lanc.name}" em {raiz}). A interface abre em http://localhost:8765')
    if os.name == 'nt' and sys.stdin and sys.stdin.isatty():
        input('Aperte Enter para fechar.')


def main() -> None:
    args = sys.argv[1:]
    if '__file__' in globals() and (Path(__file__).resolve().parent / 'ptcg').is_dir():
        instalar(Path(__file__).resolve().parent, args)           # programa já baixado
        return
    destino = Path.cwd() / 'poketrainer'                          # modo "um comando": baixa e instala
    if destino.exists() and any(destino.iterdir()):
        falhar(f'a pasta {destino} já existe. Para reinstalar/atualizar, entre nela e rode: python instalar.py')
    baixar_programa(destino)
    # roda o instalador baixado (mesmo caminho de código), preservando as opções
    sys.exit(subprocess.run([sys.executable, str(destino / 'instalar.py'), *args]).returncode)


if __name__ == '__main__' or '__file__' not in globals():
    main()
