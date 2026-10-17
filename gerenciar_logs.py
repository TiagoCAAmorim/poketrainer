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
"""
import argparse
import glob
import json
import pickle
import sys
from pathlib import Path

from ptcg.logbook import (LOG_DIR, ler_jsonl, logs_tcglive, registrar, rever_partida, salvar_log_tcglive,
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
