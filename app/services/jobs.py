from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import count

_contador = count(1)
_jobs: dict[int, "Job"] = {}


@dataclass
class Job:
    id: int
    tipo: str
    estado: str = "en_proceso"
    mensaje: str | None = None
    detalle: dict | None = None
    creado_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    terminado_en: datetime | None = None


def crear(tipo: str) -> Job:
    job = Job(id=next(_contador), tipo=tipo)
    _jobs[job.id] = job
    return job


def obtener(job_id: int) -> Job | None:
    return _jobs.get(job_id)


def listar(limit: int = 20) -> list[Job]:
    return sorted(_jobs.values(), key=lambda j: j.id, reverse=True)[:limit]


def completar(job: Job, detalle: dict | None = None) -> Job:
    job.estado = "completado"
    job.detalle = detalle
    job.terminado_en = datetime.now(timezone.utc)
    return job


def fallar(job: Job, mensaje: str) -> Job:
    job.estado = "error"
    job.mensaje = mensaje
    job.terminado_en = datetime.now(timezone.utc)
    return job
