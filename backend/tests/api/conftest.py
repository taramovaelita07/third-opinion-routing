"""Isolated persistence for every API test."""

import pytest

from app.main import app
from app.persistence import AnalysisRepository


@pytest.fixture(autouse=True)
def isolated_api_repository(tmp_path):
    repository = AnalysisRepository(tmp_path / "api-test.sqlite3")
    repository.initialize()
    app.state.analysis_repository = repository
    yield repository

