import math

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def total_pages(total: int, page_size: int) -> int:
    return math.ceil(total / page_size) if page_size else 0


def paginar(db: Session, stmt: Select, page: int, page_size: int) -> tuple[list, int]:
    subq = stmt.order_by(None).subquery()
    total = db.scalar(select(func.count()).select_from(subq)) or 0
    rows = (
        db.execute(stmt.limit(page_size).offset((page - 1) * page_size))
        .mappings()
        .all()
    )
    return rows, total


def construir_page(db: Session, stmt: Select, modelo, page: int, page_size: int) -> dict:
    rows, total = paginar(db, stmt, page, page_size)
    items = [modelo.model_validate(dict(row)) for row in rows]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": total_pages(total, page_size),
    }
