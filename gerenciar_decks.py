"""Cria, importa, edita, exporta e guarda decks (pasta decks/).

Os decks ficam em arquivos de texto no formato do Pokémon TCG Live (importáveis no jogo):
    decks/meus/            seus decks
    decks/importados/      listas importadas de arquivos
    decks/limitless/       top 8 de torneios baixados da Limitless (import_limitless.py)

Exemplos:
    python gerenciar_decks.py listar
    python gerenciar_decks.py mostrar 01_hedrick_dragapult
    python gerenciar_decks.py criar meu_dragapult --arquivo lista.txt     (lista exportada do TCG Live/Limitless)
    python gerenciar_decks.py criar meu_dragapult < lista.txt
    python gerenciar_decks.py montar meu_deck                               (montagem interativa, carta a carta)
    python gerenciar_decks.py importar pasta_com_listas/*.txt
    python gerenciar_decks.py editar meu_dragapult --add "1 Boss's Orders" --remove "1 Switch"
    python gerenciar_decks.py copiar 01_hedrick_dragapult meu_teste
    python gerenciar_decks.py exportar meu_dragapult                        (texto para colar no TCG Live)
    python gerenciar_decks.py validar --todos
    python gerenciar_decks.py apagar meu_teste
    python gerenciar_decks.py limitless import --latest 5                   (repassa para import_limitless.py)
"""
import argparse
import re
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from ptcg.carddb import db
from ptcg.decks import DECK_DIR, deck_to_text, list_decks, load_deck, parse_decklist, support_report, validate
from ptcg.logbook import registrar

ROOT = Path(__file__).resolve().parent


def safe_name(s):
    s = re.sub(r'[^\w\-]+', '_', s.strip(), flags=re.UNICODE).strip('_')
    return s or 'deck'


def deck_path(name) -> Path:
    """Arquivo de um deck pelo nome (com ou sem pasta). Novos decks vão para decks/meus/."""
    p = Path(name)
    if p.suffix == '.txt' and p.exists():
        return p
    for cand in (DECK_DIR / f'{name}.txt', DECK_DIR / 'meus' / f'{name}.txt'):
        if cand.exists():
            return cand
    hits = list(DECK_DIR.rglob(f'{Path(name).name}.txt'))
    if hits:
        return hits[0]
    return DECK_DIR / ('meus' if '/' not in name else '') / f'{name}.txt'


def save(path: Path, cards, meta, overwrite=True):
    if path.exists() and not overwrite:
        sys.exit(f'Já existe {path.relative_to(ROOT)} (use --sobrescrever).')
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in meta.items() if k not in ('errors', 'path')}
    meta.setdefault('formato', 'TEF-30C (H/I/J)')
    meta['atualizado'] = date.today().isoformat()
    path.write_text(deck_to_text(cards, meta), encoding='utf-8')
    return path


def report(cards):
    errs = validate(cards)
    pend = support_report(cards)
    if errs:
        print('  ✘ ' + '\n  ✘ '.join(errs))
    else:
        print('  ✔ deck válido (60 cartas, até 4 cópias, ≥1 Básico, ≤1 ACE SPEC)')
    for d, n, st in pend:
        print(f'  ⚠ {n}× {d.name}: efeito {"parcial" if st == "partial" else "pendente"} no simulador')
    return errs


def show(cards, title=''):
    D = db()
    c = Counter(cards)
    groups = {'pokemon': [], 'trainer': [], 'energy': []}
    for cid, n in c.items():
        groups[D.get(cid).kind].append((D.get(cid), n))
    if title:
        print(title)
    for key, label in (('pokemon', 'Pokémon'), ('trainer', 'Treinadores'), ('energy', 'Energias')):
        items = sorted(groups[key], key=lambda x: (-x[1], x[0].name))
        print(f'\n{label} ({sum(n for _, n in items)})')
        for d, n in items:
            pt = f'  ({d.name_pt})' if d.name_pt and d.name_pt != d.name else ''
            print(f'  {n} {d.name} {d.prints[0].replace("-", " ", 1) if d.prints else d.id}{pt}')
    print(f'\nTotal: {len(cards)}')


def parse_or_die(text, name):
    deck, errs = parse_decklist(text, name)
    bad = [e for e in errs]
    if bad:
        print('Problemas na lista:\n  ' + '\n  '.join(bad))
    return deck, bad


def apply_edits(cards, add, remove):
    cards = list(cards)
    for line in remove or []:
        d, _ = parse_decklist(line)
        for cid in d.cards:
            name = db().get(cid).name
            idx = next((i for i, x in enumerate(cards) if db().get(x).name == name), None)
            if idx is None:
                print(f'  aviso: {name} não está no deck')
            else:
                cards.pop(idx)
    for line in add or []:
        d, errs = parse_decklist(line)
        for e in errs:
            print('  ' + e)
        cards += d.cards
    return cards


def interactive(name, start=None):
    D = db()
    cards = list(start or [])
    print('Montagem interativa. Comandos:')
    print('  4 Ultra Ball | 4 Ultra Bola | 2 Dragapult ex TWM 130   adiciona')
    print('  -1 Ultra Ball                                             remove')
    print('  ? texto     busca cartas      ver     mostra o deck      salvar     grava e sai      sair')
    while True:
        try:
            line = input(f'[{len(cards)}/60] > ').strip()
        except EOFError:
            line = 'salvar'
        if not line:
            continue
        if line in ('sair', 'q'):
            return None
        if line == 'ver':
            show(cards)
            report(cards)
            continue
        if line == 'salvar':
            return cards
        if line.startswith('?'):
            q = line[1:].strip().lower()
            hits = [d for d in D.cards.values() if q in d.name.lower() or q in (d.name_pt or '').lower()][:25]
            for d in hits:
                print(f'  {d.name} {d.prints[0].replace("-", " ", 1)}  ({d.name_pt})  [{d.kind}]')
            continue
        if line.startswith('-'):
            cards = apply_edits(cards, [], [line[1:].strip()])
            continue
        if not re.match(r'^\d', line):
            line = '1 ' + line
        cards = apply_edits(cards, [line], [])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('listar')
    p.add_argument('--pasta', default=None)
    p = sub.add_parser('mostrar')
    p.add_argument('nome')
    p = sub.add_parser('criar')
    p.add_argument('nome')
    p.add_argument('--arquivo')
    p.add_argument('--arquetipo', default=None)
    p.add_argument('--sobrescrever', action='store_true')
    p = sub.add_parser('montar')
    p.add_argument('nome')
    p.add_argument('--base', default=None, help='começar a partir de outro deck')
    p = sub.add_parser('importar')
    p.add_argument('arquivos', nargs='+')
    p.add_argument('--pasta', default='importados')
    p = sub.add_parser('editar')
    p.add_argument('nome')
    p.add_argument('--add', nargs='*', default=[])
    p.add_argument('--remove', nargs='*', default=[])
    p = sub.add_parser('copiar')
    p.add_argument('origem')
    p.add_argument('destino')
    p = sub.add_parser('apagar')
    p.add_argument('nome')
    p = sub.add_parser('exportar')
    p.add_argument('nome')
    p.add_argument('--saida', default=None)
    p = sub.add_parser('validar')
    p.add_argument('nome', nargs='?')
    p.add_argument('--todos', action='store_true')
    p = sub.add_parser('limitless')
    p.add_argument('resto', nargs=argparse.REMAINDER)
    a = ap.parse_args()

    if a.cmd == 'listar':
        names = list_decks(a.pasta)
        for n in names:
            try:
                d = load_deck(n, strict=False)
                ok = '✔' if not d.meta['errors'] else '✘'
                pend = len(support_report(d.cards))
                arch = d.meta.get('archetype') or d.meta.get('arquetipo') or ''
                print(f'{ok} {n:<62} {arch:<28} {"(" + str(pend) + " cartas com efeito parcial)" if pend else ""}')
            except Exception as e:
                print(f'✘ {n:<62} erro: {e}')
        print(f'{len(names)} deck(s)')
    elif a.cmd == 'mostrar':
        d = load_deck(str(deck_path(a.nome)), strict=False)
        meta = {k: v for k, v in d.meta.items() if k not in ('errors', 'path')}
        show(d.cards, f'{d.name}  {meta}')
        report(d.cards)
    elif a.cmd == 'criar':
        text = Path(a.arquivo).read_text(encoding='utf-8') if a.arquivo else sys.stdin.read()
        deck, bad = parse_or_die(text, a.nome)
        meta = dict(deck.meta)
        if a.arquetipo:
            meta['archetype'] = a.arquetipo
        path = save(DECK_DIR / 'meus' / f'{safe_name(a.nome)}.txt', deck.cards, meta, a.sobrescrever)
        print(f'Deck salvo em {path.relative_to(ROOT)}')
        errs = report(deck.cards)
        registrar('decks', f'criou {path.relative_to(DECK_DIR)} ({len(deck.cards)} cartas)', erros=errs + bad)
    elif a.cmd == 'montar':
        start = load_deck(str(deck_path(a.base)), strict=False).cards if a.base else None
        cards = interactive(a.nome, start)
        if cards is None:
            print('Nada salvo.')
            return
        path = save(DECK_DIR / 'meus' / f'{safe_name(a.nome)}.txt', cards, {})
        print(f'Deck salvo em {path.relative_to(ROOT)}')
        report(cards)
        registrar('decks', f'montou {path.relative_to(DECK_DIR)} ({len(cards)} cartas)')
    elif a.cmd == 'importar':
        for f in a.arquivos:
            fp = Path(f)
            deck, bad = parse_or_die(fp.read_text(encoding='utf-8'), fp.stem)
            path = save(DECK_DIR / a.pasta / f'{safe_name(fp.stem)}.txt', deck.cards, deck.meta)
            print(f'{fp} → {path.relative_to(ROOT)}  ({len(deck.cards)} cartas)')
            errs = report(deck.cards)
            registrar('decks', f'importou {fp.name} → {path.relative_to(DECK_DIR)}', erros=errs + bad)
    elif a.cmd == 'editar':
        path = deck_path(a.nome)
        d = load_deck(str(path), strict=False)
        cards = apply_edits(d.cards, a.add, a.remove)
        save(path, cards, d.meta)
        print(f'{path.relative_to(ROOT)} atualizado ({len(cards)} cartas)')
        report(cards)
        registrar('decks', f'editou {path.relative_to(DECK_DIR)}', adicionou=a.add, removeu=a.remove)
    elif a.cmd == 'copiar':
        d = load_deck(str(deck_path(a.origem)), strict=False)
        meta = dict(d.meta)
        meta['copiado_de'] = d.name
        path = save(DECK_DIR / 'meus' / f'{safe_name(a.destino)}.txt', d.cards, meta, overwrite=False)
        print(f'Cópia salva em {path.relative_to(ROOT)}')
        registrar('decks', f'copiou {d.name} → {path.relative_to(DECK_DIR)}')
    elif a.cmd == 'apagar':
        path = deck_path(a.nome)
        if not path.exists():
            sys.exit('Deck não encontrado.')
        lix = DECK_DIR / '_lixeira'
        lix.mkdir(exist_ok=True)
        dst = lix / path.name
        path.replace(dst)
        print(f'{path.relative_to(ROOT)} movido para {dst.relative_to(ROOT)}')
        registrar('decks', f'apagou {path.relative_to(DECK_DIR)} (movido para a lixeira)')
    elif a.cmd == 'exportar':
        d = load_deck(str(deck_path(a.nome)), strict=False)
        txt = deck_to_text(d.cards)
        if a.saida:
            Path(a.saida).write_text(txt, encoding='utf-8')
            print(f'Lista exportada para {a.saida}')
        else:
            print(txt)
        registrar('decks', f'exportou {d.name}')
    elif a.cmd == 'validar':
        names = list_decks() if a.todos or not a.nome else [a.nome]
        bad = 0
        for n in names:
            d = load_deck(str(deck_path(n)), strict=False)
            print(n)
            bad += bool(report(d.cards))
        print(f'{len(names) - bad}/{len(names)} válidos')
    elif a.cmd == 'limitless':
        subprocess.run([sys.executable, str(ROOT / 'import_limitless.py')] + a.resto)
        registrar('decks', 'importação da Limitless: ' + ' '.join(a.resto))


if __name__ == '__main__':
    main()
