from __future__ import annotations

import csv
from pathlib import Path
from threading import RLock

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.csv_storage import export_csv, import_csv
from app.manager import SalaryManager


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
MAX_IMPORT_SIZE = 5 * 1024 * 1024


class PositionPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RulePayload(BaseModel):
    level: int = Field(ge=1, le=4)
    base_salary: float
    bonus: float
    from_position: str | None = None
    from_level: int | None = Field(default=None, ge=1, le=4)
    formula_salary: str = ""
    formula_bonus: str = ""


class RulesPayload(BaseModel):
    rules: list[RulePayload]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Salary Dependency Manager",
        description="Керування зарплатами та залежностями між рівнями посад.",
        version="1.0.0",
    )
    app.state.manager = SalaryManager()
    app.state.lock = RLock()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/state")
    def get_state(request: Request) -> dict:
        with request.app.state.lock:
            return request.app.state.manager.to_dict()

    @app.post("/api/positions", status_code=status.HTTP_201_CREATED)
    def add_position(payload: PositionPayload, request: Request) -> dict:
        with request.app.state.lock:
            try:
                request.app.state.manager.add_position(payload.name)
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return request.app.state.manager.to_dict()

    @app.delete("/api/positions/{position_name}")
    def remove_position(position_name: str, request: Request) -> dict:
        with request.app.state.lock:
            try:
                request.app.state.manager.remove_position(position_name)
            except ValueError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            return request.app.state.manager.to_dict()

    @app.put("/api/positions/{position_name}/rules")
    def update_rules(
        position_name: str,
        payload: RulesPayload,
        request: Request,
    ) -> dict:
        with request.app.state.lock:
            try:
                request.app.state.manager.update_rules(
                    position_name,
                    [rule.model_dump() for rule in payload.rules],
                )
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return request.app.state.manager.to_dict()

    @app.get("/api/export")
    def download_csv(request: Request) -> Response:
        with request.app.state.lock:
            content = export_csv(request.app.state.manager)
        return Response(
            content=content.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="salary_dependency_manager.csv"'
            },
        )

    @app.post("/api/import")
    async def upload_csv(request: Request) -> dict:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                is_too_large = int(content_length) > MAX_IMPORT_SIZE
            except ValueError:
                is_too_large = False
            if is_too_large:
                raise HTTPException(status_code=413, detail="CSV-файл перевищує ліміт 5 МБ.")

        raw_content = await request.body()
        if len(raw_content) > MAX_IMPORT_SIZE:
            raise HTTPException(status_code=413, detail="CSV-файл перевищує ліміт 5 МБ.")
        try:
            content = raw_content.decode("utf-8-sig")
            loaded_manager = import_csv(content)
        except UnicodeError as error:
            raise HTTPException(status_code=400, detail="CSV повинен мати кодування UTF-8.") from error
        except (ValueError, csv.Error) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        with request.app.state.lock:
            request.app.state.manager = loaded_manager
            return request.app.state.manager.to_dict()

    return app


app = create_app()
