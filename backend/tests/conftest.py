"""Shared test setup.

The shipped catalog is empty (live-first), so tests load the curated *sample*
catalog instead, disable disk persistence, and disable the live client so the
suite is fully offline and deterministic. Live behaviour is tested separately in
test_live.py using stubbed fixtures.
"""
import pytest

from app import tools


@pytest.fixture(autouse=True)
def seeded_offline_repo():
    tools.repo.persist = False
    tools.repo.live.enabled = False  # no network during tests
    tools.repo.load_sample()
    yield
