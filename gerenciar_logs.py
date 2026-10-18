"""LOG: guarda e consulta partidas do Pokémon TCG Live, simulações e o registro de atividade (pasta logs/).

Exemplos:
    python gerenciar_logs.py importar partida1.txt partida2.txt     guarda logs do TCG Live ("Copy Log") e os
                                                                   reproduz no motor, conferindo cada jogada
    python gerenciar_logs.py listar                                 resumo de tudo o que está guardado
    python gerenciar_logs.py listar tcglive
    python gerenciar_logs.py listar simulacoes
    python gerenciar_logs.py mostrar 2026-10-17_190000_Fulano_vs_Ciclano      relatório da reprodução
    python gerenciar_logs.py rever logs/simulacoes/<arquivo>.jsonl --partida 3  refaz uma partida simulada
    python gerenciar_logs.py atividade --ultimos 30                 últimos eventos do registro
    python gerenciar_logs.py reprocessar                            reproduz de novo todos os logs do TCG Live
    python gerenciar_logs.py imitacao dados/imitacao.pkl             amostras (estado, jogada) de todos os logs
    python gerenciar_logs.py fixar                                   copia partidas da interface sem comentários para
                                                                   tests/fixtures/partidas/ (viram teste do motor)
    python gerenciar_logs.py problemas [abertos|corrigidos|todos]    comentários feitos nas partidas (logs/problemas.jsonl)
    python gerenciar_logs.py problema P003                           detalhe + últimas linhas da partida
    python gerenciar_logs.py corrigir P003 --nota "o que foi feito"  marca como corrigido (depois de testar!)
    python gerenciar_logs.py reabrir P003
"""
import argparse
import glob
import json
import pickle
import sys
from pathlib import Path

from ptcg.logbook import (LOG_DIR, atualizar_problema, problemas, ler_jsonl, logs_tcglive, registrar, rever_partida, salvar_log_tcglive,
                          sessoes_simulacao)


def importar(files, record=False):
    from ptcg.replay.replay import replay_log
    samples = []
    for f in files:
        text = Path(f).read_text(encoding='utf-8')
        try:
            rep = replay_log(text, record=record)
        except Exception as e:
            print(f'{f}: não consegui ler o log ({type(e).__name__}: {e})')
            salvar_log_tcglive(text, None, origem=str(f))
            continue
        p = salvar_log_tcglive(text, rep, origem=str(f))
        ok = rep.finished and not rep.divergence
        print(f'{f} → {p.relative_to(LOG_DIR.parent)}')
        print(f'   ações {rep.actions_done}/{rep.actions_total} · '
              f'{"reproduzida até o fim" if ok else "divergência: " + str(rep.divergence)}')
        samples += [(o, i, pl, p.name) for o, i, pl in rep.samples]
    return samples


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('importar')
    p.add_argument('arquivos', nargs='+')
    p = sub.add_parser('listar')
    p.add_argument('o_que', nargs='?', choices=['tcglive', 'simulacoes', 'interface'], default=None)
    p = sub.add_parser('mostrar')
    p.add_argument('nome')
    p = sub.add_parser('rever')
    p.add_argument('arquivo')
    p.add_argument('--partida', type=int, default=1, help='número da partida no arquivo (1 = primeira)')
    p = sub.add_parser('atividade')
    p.add_argument('--ultimos', type=int, default=40)
    sub.add_parser('reprocessar')
    sub.add_parser('fixar')
    p = sub.add_parser('problemas')
    p.add_argument('filtro', nargs='?', choices=['abertos', 'corrigidos', 'todos'], default='abertos')
    p = sub.add_parser('problema')
    p.add_argument('id')
    p = sub.add_parser('corrigir')
    p.add_argument('id')
    p.add_argument('--nota', required=True, help='o que foi corrigido (e onde)')
    p = sub.add_parser('reabrir')
    p.add_argument('id')
    p = sub.add_parser('imitacao')
    p.add_argument('saida')
    a = ap.parse_args()

    if a.cmd == 'importar':
        files = [f for pat in a.arquivos for f in (glob.glob(pat) or [pat])]
        importar(files)
    elif a.cmd == 'listar':
        if a.o_que in (None, 'tcglive'):
            rows = logs_tcglive()
            print(f'Partidas do TCG Live ({len(rows)}) — logs/partidas_tcglive/')
            for r in rows:
                st = '✔' if r.get('completo') else ('✘' if 'completo' in r else '?')
                ac = r.get('acoes') or ['?', '?']
                print(f"  {st} {Path(r['arquivo']).stem:<60} {' x '.join(r.get('jogadores') or [])}  "
                      f"ações {ac[0]}/{ac[1]}")
        if a.o_que in (None, 'simulacoes'):
            ss = sessoes_simulacao()
            print(f'\nSimulações ({len(ss)} arquivos) — logs/simulacoes/')
            for s in ss:
                recs = ler_jsonl(s)
                print(f'  {s.name:<75} {len(recs)} partidas')
        if a.o_que in (None, 'interface'):
            recs = ler_jsonl(LOG_DIR / 'interface' / 'partidas.jsonl')
            print(f'\nPartidas na interface ({len(recs)}) — logs/interface/partidas.jsonl')
            for i, r in enumerate(recs[-15:], 1):
                w = 'empate' if r['vencedor'] == -1 else r['jogadores'][r['vencedor']]
                print(f"  {r['quando']}  {' x '.join(r['jogadores'])}  → {w} ({r['motivo']}, {r['turnos']} turnos)")
    elif a.cmd == 'mostrar':
        d = LOG_DIR / 'partidas_tcglive'
        hits = sorted(d.glob(f'*{a.nome}*.json'))
        if not hits:
            sys.exit('Log não encontrado (veja `listar tcglive`).')
        info = json.loads(hits[0].read_text(encoding='utf-8'))
        print(hits[0].with_suffix('.txt'))
        print(info['resumo'])
    elif a.cmd == 'rever':
        recs = ler_jsonl(a.arquivo)
        if not recs:
            sys.exit('Arquivo vazio ou inexistente.')
        rec = recs[a.partida - 1]
        g = rever_partida(rec)
        for x in g.log:
            print(x['msg'])
        same = g.winner == rec['vencedor'] and g.turn == rec['turnos']
        print(f'\nResultado: {g.end_reason} · igual ao gravado: {"sim" if same else "NÃO"}')
    elif a.cmd == 'atividade':
        p = LOG_DIR / 'atividade.log'
        lines = p.read_text(encoding='utf-8').splitlines() if p.exists() else []
        print('\n'.join(lines[-a.ultimos:]) or '(vazio)')
    elif a.cmd == 'fixar':
        dest = Path(__file__).resolve().parent / 'tests' / 'fixtures' / 'partidas' / 'interface.jsonl'
        dest.parent.mkdir(parents=True, exist_ok=True)
        ja = {(r['semente'], tuple(r['history'])) for r in ler_jsonl(dest)}
        novas = [r for r in ler_jsonl(LOG_DIR / 'interface' / 'partidas.jsonl')
                 if r.get('history') and not r.get('comentarios') and (r['semente'], tuple(r['history'])) not in ja]
        from tests.test_partidas_usuario import refazer
        validas = []
        for r in novas:
            try:
                g = refazer(r)
                if g.winner == r['vencedor'] and g.turn == r['turnos']:
                    validas.append(r)
                    continue
            except AssertionError:
                pass
            print(f'ignorada (não reproduz mais no motor atual): {r["quando"]} {r["jogadores"]}')
        novas = validas
        with open(dest, 'a', encoding='utf-8') as f:
            for r in novas:
                r.pop('log', None)
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        print(f'{len(novas)} partidas novas em {dest.relative_to(Path(__file__).resolve().parent)}')
    elif a.cmd == 'problemas':
        st = {'abertos': 'aberto', 'corrigidos': 'corrigido', 'todos': None}[a.filtro]
        rows = problemas(st)
        for r in rows:
            print(f'{r["id"]} [{r["status"]}] {r["quando"][:10]} turno {r["turno"]}: {r["texto"]}')
        print(f'({len(rows)} {a.filtro})')
    elif a.cmd == 'problema':
        r = next((x for x in problemas() if x['id'] == a.id.upper()), None)
        if r is None:
            sys.exit('problema não encontrado')
        print(f'{r["id"]} [{r["status"]}] {r["quando"]} — {r["jogadores"]} decks={r["decks"]} semente={r["semente"]}')
        print(f'Comentário: {r["texto"]}\n')
        if r.get('prompt'):
            print(f'Decisão {r["decisao"]} (turno {r["turno"]}): {r["prompt"]["texto"]}')
            for o in r['prompt']['opcoes']:
                print(f'   - {o}')
        print('\nÚltimas linhas:')
        for m in r['ultimas_linhas']:
            print('  ', m)
        if r.get('correcao'):
            print(f'\nCorreção: {r["correcao"]}')
        print('\nPara reproduzir: rever_partida(registro) com ptcg.logbook (decks_ids, semente, history).')
    elif a.cmd in ('corrigir', 'reabrir'):
        try:
            r = atualizar_problema(a.id, 'corrigido' if a.cmd == 'corrigir' else 'aberto', getattr(a, 'nota', ''))
        except KeyError as e:
            sys.exit(str(e))
        print(f'{r["id"]} → {r["status"]}')
    elif a.cmd == 'reprocessar':
        d = LOG_DIR / 'partidas_tcglive'
        files = sorted(d.glob('*.txt'))
        importar(files)
        registrar('tcglive', f'reprocessou {len(files)} logs')
    elif a.cmd == 'imitacao':
        d = LOG_DIR / 'partidas_tcglive'
        samples = importar(sorted(d.glob('*.txt')), record=True)
        Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
        with open(a.saida, 'wb') as f:
            pickle.dump(samples, f)
        print(f'{len(samples)} amostras salvas em {a.saida}')
        registrar('tcglive', f'gerou {len(samples)} amostras de imitação em {a.saida}')


if __name__ == '__main__':
    main()
