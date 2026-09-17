from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from board.db import get_db

router = APIRouter()


@router.get("/health")
def health(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
        db_status = "ok"
    except SQLAlchemyError:
        db_status = "error"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if db_status == "ok" else "error",
        "version": request.app.version,
        "db": db_status,
    }
