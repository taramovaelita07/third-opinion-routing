"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.persistence import AnalysisRepository, PersistenceError

APP_NAME = "Third Opinion Routing API"
APP_VERSION = "1.4.0"
FRONTEND_DIRECTORY = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(application: FastAPI):
    repository = AnalysisRepository.from_environment()
    repository.initialize()
    application.state.analysis_repository = repository
    yield

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=(
        "Transforms existing radiology AI results into safe, explainable "
        "draft routing recommendations for clinical review."
    ),
    lifespan=lifespan,
)

app.include_router(api_router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIRECTORY), name="static")


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    _request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    """Return a stable Russian error contract without echoing medical input."""

    validation_errors = [
        {
            "type": error["type"],
            "location": list(error["loc"]),
            "message": error["msg"],
        }
        for error in exception.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": {
                "code": "REQUEST_VALIDATION_ERROR",
                "message": "Проверьте формат и обязательные поля запроса",
                "validation_errors": validation_errors,
            }
        },
    )


@app.exception_handler(PersistenceError)
async def persistence_error(
    _request: Request,
    _exception: PersistenceError,
) -> JSONResponse:
    """Keep storage failures understandable without exposing internals."""

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": {
                "code": "STORED_DATA_INVALID",
                "message": "Сохранённые данные повреждены и не могут быть открыты",
            }
        },
    )


@app.get("/", include_in_schema=False)
@app.get("/app", include_in_schema=False)
def frontend() -> FileResponse:
    """Serve the offline clinician workspace from the same process."""

    return FileResponse(FRONTEND_DIRECTORY / "index.html")


@app.get("/patient", include_in_schema=False)
def patient_frontend() -> FileResponse:
    """Serve the patient-owned booking workspace."""

    return FileResponse(FRONTEND_DIRECTORY / "patient.html")


@app.get("/api-info", tags=["system"])
def service_info() -> dict[str, str]:
    return {
        "service": "third-opinion-routing-api",
        "version": APP_VERSION,
        "interface": "/",
        "patient_interface": "/patient",
        "documentation": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Return a lightweight liveness response for local and Docker checks."""

    return {
        "status": "ok",
        "service": "third-opinion-routing-api",
        "version": APP_VERSION,
    }
