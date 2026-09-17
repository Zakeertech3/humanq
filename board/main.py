from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from board.config import Settings, get_settings
from board.db import get_db, init_db, make_engine
from board.routes.agents import router as agents_router
from board.routes.health import router as health_router
from board.routes.requests import router as requests_router

STATIC_DIR = Path(__file__).parent / "static"


def package_version() -> str:
    try:
        return version("humanq-board")
    except PackageNotFoundError:
        return "0.0.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active = settings if settings is not None else get_settings()
        engine = make_engine(active.board_db_path)
        init_db(engine)
        app.state.settings = active
        app.state.engine = engine

        def session_dependency() -> Iterator[Session]:
            session = Session(engine)
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = session_dependency
        app.dependency_overrides[get_settings] = lambda: active
        yield
        engine.dispose()

    app = FastAPI(title="humanq", version=package_version(), lifespan=lifespan)
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(health_router)
    app.include_router(agents_router)
    app.include_router(requests_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    runtime_settings = get_settings()
    uvicorn.run(app, host=runtime_settings.board_host, port=runtime_settings.board_port)
