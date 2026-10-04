"""Static guarantees for the reproducible Docker deployment."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _read(name: str) -> str:
    return (PROJECT_ROOT / name).read_text(encoding="utf-8")


def test_dockerfile_packages_the_complete_offline_application() -> None:
    dockerfile = _read("Dockerfile")

    assert "FROM python:3.13-slim" in dockerfile
    assert "COPY backend/app /app/backend/app" in dockerfile
    assert "COPY frontend /app/frontend" in dockerfile
    assert "COPY data/demo /app/data/demo" in dockerfile
    assert "app.main:app --host 0.0.0.0" in dockerfile
    assert "${PORT:-8000}" in dockerfile


def test_container_runs_as_non_root_and_has_healthcheck() -> None:
    dockerfile = _read("Dockerfile")

    assert "USER appuser" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "os.getenv('PORT', '8000')" in dockerfile


def test_compose_keeps_database_in_a_named_volume() -> None:
    compose = _read("compose.yaml")

    assert '"127.0.0.1:8000:8000"' in compose
    assert "DATABASE_PATH: /app/storage/third_opinion.sqlite3" in compose
    assert "third_opinion_data:/app/storage" in compose
    assert "third_opinion_data:" in compose


def test_docker_context_excludes_local_and_patient_state() -> None:
    dockerignore = _read(".dockerignore")

    assert "backend/.venv" in dockerignore
    assert "*.sqlite3" in dockerignore
    assert "**/__pycache__" in dockerignore


def test_offline_hackathon_runbook_covers_launch_demo_and_recovery() -> None:
    runbook = _read("HACKATHON_RUNBOOK_RU.md")

    assert "docker compose up --build" in runbook
    assert "http://localhost:8000/patient" in runbook
    assert "Сценарий показа жюри" in runbook
    assert "Сбросить демо" in runbook
    assert "Быстрое восстановление" in runbook


def test_render_blueprint_exposes_the_same_docker_application() -> None:
    blueprint = _read("render.yaml")

    assert "type: web" in blueprint
    assert "runtime: docker" in blueprint
    assert "plan: free" in blueprint
    assert "healthCheckPath: /health" in blueprint
    assert "DATABASE_PATH" in blueprint
    assert "/tmp/third_opinion.sqlite3" in blueprint
