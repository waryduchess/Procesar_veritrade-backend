from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session
from groq import APIStatusError, RateLimitError

from app.config import settings
from app.services import llm
from app.services.tools import TOOLS, TOOL_DEFINITIONS

ESQUEMA_FILE = Path(__file__).resolve().parent.parent / "data" / "esquema.json"

SIN_DATO = "No tengo ese dato en la base de datos."

_SALUDOS = {
    "hola",
    "buen",
    "buenos",
    "buenas",
    "dia",
    "dias",
    "tarde",
    "tardes",
    "noche",
    "noches",
    "hey",
    "saludos",
    "que",
    "tal",
    "como",
    "estas",
    "andas",
    "gracias",
}


def _normalizar(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.lower())
    limpio = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", limpio).strip()


def _es_saludo(texto: str) -> bool:
    palabras = _normalizar(texto).split()
    return bool(palabras) and len(palabras) <= 5 and all(
        p in _SALUDOS for p in palabras
    )


class AgenteError(RuntimeError):
    pass


class AgenteLimite(AgenteError):
    pass


@lru_cache(maxsize=1)
def _esquema() -> str:
    return ESQUEMA_FILE.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return f"""Eres un analista de datos de importaciones de Veritrade México.
Tu única fuente de verdad es la base de datos, a la que accedes mediante herramientas (tools).

REGLAS OBLIGATORIAS:
1. Para responder cualquier pregunta sobre datos, primero llama a una o más herramientas. Nunca respondas de memoria.
2. Solo puedes afirmar cifras, nombres y hechos que aparezcan en los resultados de las herramientas.
3. Si la pregunta requiere datos y las herramientas no los cubren, responde exactamente: "{SIN_DATO}" y no inventes nada.
4. No inventes columnas, productos, empresas ni valores. No supongas datos que no estén en los resultados.
5. Si piden algo fuera de importaciones (clima, política, opiniones, etc.), rechaza brevemente.
6. Responde en español, claro y breve, sin emojis, incluyendo las cifras relevantes.
7. Aclara unidades: el valor es USD y el volumen es KG.
8. 'porcentaje' es % del VOLUMEN (KG); 'pct_total' es % del VALOR (USD); 'pct_acumulado' es valor acumulado (Pareto). El denominador es siempre el conjunto filtrado.
9. Para rankings usa la herramienta "ranking" con la dimension adecuada; usa top para limitar filas.
10. Si piden porcentaje/volumen/peso, ordena con order_by="volumen_kg"; si piden valor/monto/USD, usa "valor_usd".
11. Cuando filtres por un producto, usa el parámetro 'partida' para que los porcentajes se calculen sobre el total de ese producto.
12. El máximo de filas por ranking es 50. Si piden "todas" o "cada", usa top=50; si el campo total del resultado supera las filas devueltas, aclara que hay más.
13. Si el usuario solo saluda o agradece, responde cordialmente en 1-2 líneas y ofrécele ayuda con datos de importaciones. En ese caso no llames herramientas.


DICCIONARIO DE DATOS (JSON):
{_esquema()}
"""


def _mensaje_assistant(msg) -> dict:
    return {
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ],
    }


def _ejecutar_tool(db: Session, nombre: str, args: dict):
    tool = TOOLS.get(nombre)
    if tool is None:
        return {"error": f"Herramienta desconocida: {nombre}"}
    try:
        return tool.handler(db, args)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"No se pudo ejecutar {nombre}: {exc}"}


def consultar(db: Session, pregunta: str) -> dict:
    client = llm.cliente()
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": pregunta},
    ]
    llamadas: list[dict] = []
    datos: list[dict] = []

    for _ in range(max(1, settings.agente_max_tool_calls)):
        try:
            completion = client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                max_tokens=settings.agente_max_tokens,
            )
        except RateLimitError as exc:
            raise AgenteLimite(
                "Límite de tokens del modelo alcanzado. Intenta de nuevo en unos segundos."
            ) from exc
        except APIStatusError as exc:
            if exc.status_code in (413, 429):
                raise AgenteLimite(
                    "Límite de tokens del modelo alcanzado. Intenta de nuevo en unos segundos."
                ) from exc
            raise AgenteError(f"Error al consultar el modelo: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise AgenteError(f"Error al consultar el modelo: {exc}") from exc

        msg = completion.choices[0].message

        if not msg.tool_calls:
            respuesta = (msg.content or "").strip()
            if not llamadas and not _es_saludo(pregunta):
                respuesta = SIN_DATO
            return {
                "respuesta": respuesta or SIN_DATO,
                "tool_calls": llamadas,
                "datos_usados": datos,
            }

        messages.append(_mensaje_assistant(msg))

        for tc in msg.tool_calls:
            nombre = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            resultado = _ejecutar_tool(db, nombre, args)
            llamadas.append({"name": nombre, "args": args})
            datos.append({"tool": nombre, "args": args, "resultado": resultado})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": nombre,
                    "content": json.dumps(resultado, ensure_ascii=False, default=str),
                }
            )

    return {
        "respuesta": (
            "No pude completar la consulta con la información disponible. "
            "Intenta ser más específico."
        ),
        "tool_calls": llamadas,
        "datos_usados": datos,
    }
