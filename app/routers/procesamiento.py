from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.database import engine
from app.schemas import JobOut
from app.services import cargar, jobs, procesar

DIR_UPLOADS = Path("uploads")
DIR_SALIDA = Path("salida")
ARCHIVO_PROCESADO = DIR_SALIDA / "veritrade_limpio.xlsx"

router = APIRouter(prefix="/procesamiento", tags=["procesamiento"])


@router.post("/upload", response_model=JobOut)
async def subir(
    archivo: UploadFile = File(...),
    hoja: str = Query("Veritrade", description="Nombre de la hoja del Excel"),
    fila_header: int = Query(5, ge=0, description="Fila de encabezado (0-indexed)"),
) -> jobs.Job:
    job = jobs.crear("upload")
    try:
        DIR_UPLOADS.mkdir(parents=True, exist_ok=True)
        DIR_SALIDA.mkdir(parents=True, exist_ok=True)
        destino = DIR_UPLOADS / (archivo.filename or f"upload_{job.id}.xlsx")
        destino.write_bytes(await archivo.read())

        detalle = procesar.procesar(
            destino, ARCHIVO_PROCESADO, hoja=hoja, fila_header=fila_header
        )
        detalle["archivo_entrada"] = str(destino)
        return jobs.completar(job, detalle)
    except Exception as exc:
        return jobs.fallar(job, str(exc))


@router.post("/cargar", response_model=JobOut)
def cargar_mysql(
    ruta: str | None = Query(None, description="Excel procesado a cargar"),
    hoja: str = Query("Datos_Limpios"),
) -> jobs.Job:
    job = jobs.crear("cargar")
    try:
        ruta_final = Path(ruta) if ruta else ARCHIVO_PROCESADO
        if not ruta_final.exists():
            raise FileNotFoundError(f"No existe el archivo: {ruta_final}")
        detalle = cargar.cargar(ruta_final, engine, hoja=hoja)
        detalle["archivo"] = str(ruta_final)
        return jobs.completar(job, detalle)
    except Exception as exc:
        return jobs.fallar(job, str(exc))


@router.get("/status/{job_id}", response_model=JobOut)
def estado(job_id: int) -> jobs.Job:
    job = jobs.obtener(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return job


@router.get("/historial", response_model=list[JobOut])
def historial(limit: int = Query(20, ge=1, le=100)) -> list[jobs.Job]:
    return jobs.listar(limit)
