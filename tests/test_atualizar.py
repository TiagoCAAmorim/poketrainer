"""Atualização do programa (ptcg/atualizar.py): modo git (repo local como 'GitHub') e modo ZIP, preservando dados do usuário."""
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ptcg import atualizar as A


def sh(*a, cwd):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


def commit(repo, arquivos, msg):
    for rel, txt in arquivos.items():
        p = Path(repo) / rel
        if txt is None:
            p.unlink()
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(txt, encoding='utf-8')
    sh('git', 'add', '-A', cwd=repo)
    sh('git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', msg, cwd=repo)


def teste_git():
    with tempfile.TemporaryDirectory() as tmp:
        up, cl = Path(tmp, 'up'), Path(tmp, 'cl')
        up.mkdir()
        sh('git', 'init', '-q', '-b', 'main', cwd=up)
        commit(up, {'a.py': 'v1', 'ias/nivel_1.pt': 'rede1'}, 'primeiro')
        sh('git', 'clone', '-q', str(up), str(cl), cwd=tmp)
        url = str(up)
        v = A.verificar(cl, url)
        assert v['modo'] == 'git' and not v['disponivel'], v
        commit(up, {'a.py': 'v2', 'ias/nivel_2.pt': 'rede2'}, 'segundo')
        v = A.verificar(cl, url)
        assert v['disponivel'] and v['pode_atualizar'] and 'segundo' in v['novidades'][0], v
        (cl / 'meu_deck.txt').write_text('meu')                 # arquivo não rastreado do usuário
        r = A.aplicar(cl, url)
        assert r['ok'] and (cl / 'a.py').read_text() == 'v2' and (cl / 'ias/nivel_2.pt').exists()
        assert (cl / 'meu_deck.txt').read_text() == 'meu'
        assert not A.verificar(cl, url)['disponivel']
        # alteração local no mesmo arquivo que o remoto muda → erro claro, sem perder a edição
        commit(up, {'a.py': 'v3'}, 'terceiro')
        (cl / 'a.py').write_text('editado')
        try:
            A.aplicar(cl, url)
            raise AssertionError('deveria falhar')
        except A.ErroAtualizacao as e:
            assert 'alterações' in str(e)
        assert (cl / 'a.py').read_text() == 'editado'
        # branch de desenvolvimento: não atualiza
        sh('git', 'checkout', '-q', '-b', 'dev', cwd=cl)
        assert not A.verificar(cl, url)['pode_atualizar']
        try:
            A.aplicar(cl, url)
            raise AssertionError('deveria recusar')
        except A.ErroAtualizacao:
            pass


def faz_zip(path, arquivos):
    with zipfile.ZipFile(path, 'w') as z:
        for rel, txt in arquivos.items():
            z.writestr('poketrainer-main/' + rel, txt)


def teste_zip():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp, 'inst')
        raiz.mkdir()
        (raiz / 'decks/meus').mkdir(parents=True)
        (raiz / 'decks/meus/meu.txt').write_text('meu deck')
        (raiz / 'logs').mkdir()
        (raiz / 'logs/problemas.jsonl').write_text('meu log')
        z1, z2 = Path(tmp, 'v1.zip'), Path(tmp, 'v2.zip')
        faz_zip(z1, {'a.py': 'v1', 'velho.py': 'x', 'ias/nivel_1.pt': 'r1', 'decks/meus/meu.txt': 'DO ZIP', 'logs/problemas.jsonl': 'DO ZIP'})
        faz_zip(z2, {'a.py': 'v2', 'ias/nivel_1.pt': 'r1b', 'ias/nivel_2.pt': 'r2', 'logs/problemas.jsonl': 'DO ZIP'})
        A._aplicar_zip(raiz, z1.as_uri(), 'sha1')
        assert (raiz / 'a.py').read_text() == 'v1' and (raiz / 'velho.py').exists()
        assert (raiz / 'decks/meus/meu.txt').read_text() == 'meu deck'      # protegido
        assert (raiz / 'logs/problemas.jsonl').read_text() == 'meu log'
        assert A.versao_local(raiz) == {'sha': 'sha1'} or A.versao_local(raiz)['sha'] == 'sha1'
        A._aplicar_zip(raiz, z2.as_uri(), 'sha2')
        assert (raiz / 'a.py').read_text() == 'v2' and (raiz / 'ias/nivel_2.pt').read_text() == 'r2'
        assert not (raiz / 'velho.py').exists()                              # saiu do projeto
        assert (raiz / 'decks/meus/meu.txt').read_text() == 'meu deck'
        assert json.loads((raiz / A.MARCA).read_text())['sha'] == 'sha2'
        assert not list(raiz.rglob('*.novo'))
        # ZIP malicioso é recusado antes de escrever
        ruim = Path(tmp, 'ruim.zip')
        with zipfile.ZipFile(ruim, 'w') as z:
            z.writestr('p/ok.py', 'x')
            z.writestr('p/../../fora.py', 'x')
        try:
            A._aplicar_zip(raiz, ruim.as_uri(), 'x')
            raise AssertionError('deveria recusar')
        except A.ErroAtualizacao:
            pass
        assert not (raiz / 'ok.py').exists() and not Path(tmp, 'fora.py').exists()
        # verificar (zip): compara com o SHA remoto
        A._sha_remoto = lambda: {'sha': 'sha2', 'mensagem': 'm', 'data': '2026-11-14'}
        assert not A.verificar(raiz)['disponivel']
        A._sha_remoto = lambda: {'sha': 'sha3', 'mensagem': 'novo', 'data': '2026-11-15'}
        assert A.verificar(raiz)['disponivel']


if __name__ == '__main__':
    teste_git()
    teste_zip()
    print('test_atualizar: OK')
