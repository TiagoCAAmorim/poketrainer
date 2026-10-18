"""Registro dos treinos no Weights & Biases (W&B): entidade tiago-amorim, projeto poketrainer.

Opcional: sem o pacote `wandb`, sem login ou com --sem-wandb, tudo funciona igual e só o registro local
(logs/ia/treinos.jsonl) é feito. Outra entidade/projeto: variáveis WANDB_ENTITY / WANDB_PROJECT.
Para rodar sem internet: WANDB_MODE=offline (depois `wandb sync wandb/offline-run-*`).
"""
from __future__ import annotations

import os
from pathlib import Path

ENTITY = os.environ.get('WANDB_ENTITY', 'tiago-amorim')
PROJECT = os.environ.get('WANDB_PROJECT', 'poketrainer')
ROOT = Path(__file__).resolve().parents[2]


class Run:
    """Envelope que vira no-op quando o W&B está desligado ou falhou ao iniciar."""

    def __init__(self, run=None):
        self.run = run

    def __bool__(self):
        return self.run is not None

    @property
    def url(self):
        if self.run is None or getattr(self.run.settings, 'mode', None) in ('offline', 'dryrun'):
            return None
        return self.run.url

    def log(self, data: dict, step=None):
        if self.run is not None:
            self.run.log({k: v for k, v in data.items() if isinstance(v, (int, float)) and not isinstance(v, bool)},
                         step=step)

    def summary(self, data: dict):
        if self.run is not None:
            for k, v in data.items():
                if isinstance(v, (int, float, str)) and not isinstance(v, bool):
                    self.run.summary[k] = v

    def table(self, key, columns, rows):
        if self.run is not None:
            import wandb
            self.run.log({key: wandb.Table(columns=columns, data=rows)})

    def artifact(self, path, name, kind='modelo', metadata=None, aliases=None):
        """Sobe um checkpoint como artefato versionado (ex.: name='imitacao', aliases=['best'])."""
        if self.run is not None and Path(path).exists():
            import wandb
            art = wandb.Artifact(name, type=kind, metadata=_clean(metadata or {}))
            art.add_file(str(path))
            self.run.log_artifact(art, aliases=aliases)

    def finish(self, exit_code=0):
        if self.run is not None:
            self.run.finish(exit_code=exit_code)
            self.run = None


def _clean(d):
    return {k: (v if isinstance(v, (int, float, str, bool, type(None), list, dict)) else str(v)) for k, v in d.items()}


def start(job_type: str, config: dict, name=None, enabled=True, tags=None, log=print) -> Run:
    """Abre uma execução no W&B (job_type: dados | imitacao | avaliacao | ppo). Falhas viram aviso, nunca erro."""
    if not enabled or os.environ.get('WANDB_MODE') == 'disabled':
        return Run()
    try:
        import wandb
    except ImportError:
        log('W&B: pacote wandb não instalado (pip install wandb) — registrando só em logs/ia/treinos.jsonl')
        return Run()
    try:
        run = wandb.init(entity=ENTITY, project=PROJECT, job_type=job_type, name=name, config=_clean(config),
                         tags=tags, dir=str(ROOT), reinit='finish_previous')
        log(f'W&B: {run.url}')
        return Run(run)
    except Exception as e:      # sem login, sem rede etc.: o treino continua
        log(f'W&B indisponível ({type(e).__name__}: {e}) — registrando só em logs/ia/treinos.jsonl')
        return Run()
