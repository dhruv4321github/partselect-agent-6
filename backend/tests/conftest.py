"""Shared test setup.

Tests seed the repo with a minimal fixture part and model, disable disk
persistence, and disable the live client so the suite is fully offline
and deterministic.
"""
import pytest

from app import tools

FIXTURE_PART = {
    "ps_number": "PS11752778",
    "mfr_number": "WPW10321304",
    "name": "Refrigerator Door Shelf Bin",
    "brand": "Whirlpool",
    "appliance_type": "Refrigerator",
    "category": "Shelves & Bins",
    "price": 36.62,
    "in_stock": True,
    "rating": 5.0,
    "review_count": 264,
    "image_url": "",
    "url": "https://www.partselect.com/PS11752778-Whirlpool-WPW10321304-Refrigerator-Door-Shelf-Bin.htm",
    "description": "Refrigerator door shelf bin.",
    "symptoms_fixed": ["Door won't open or close", "Ice maker won't dispense ice", "Leaking"],
    "compatible_products": ["Whirlpool", "Kenmore"],
    "compatible_models": ["WRS325SDHZ08"],
    "replaces_parts": ["AP6019471"],
    "install": {
        "difficulty": "Easy",
        "time_estimate": "Less than 15 minutes",
        "tools_required": [],
        "steps": ["Remove old bin.", "Snap new bin into place."],
    },
    "verified": True,
    "source": "test",
}

FIXTURE_MODEL = {
    "model_number": "WDT780SAEM1",
    "brand": "Whirlpool",
    "appliance_type": "Dishwasher",
    "compatible_parts": ["PS11752778"],
}


@pytest.fixture(autouse=True)
def seeded_offline_repo():
    tools.repo.persist = False
    tools.repo.live.enabled = False

    tools.repo.parts = [FIXTURE_PART]
    tools.repo.models = {FIXTURE_MODEL["model_number"].upper(): FIXTURE_MODEL}
    tools.repo._by_ps = {FIXTURE_PART["ps_number"].upper(): FIXTURE_PART}
    tools.repo._by_mfr = {FIXTURE_PART["mfr_number"].upper(): FIXTURE_PART}
    tools.repo._by_replaces = {rp.strip().upper(): FIXTURE_PART
                                for rp in FIXTURE_PART.get("replaces_parts", [])}
    from app.search import SearchIndex
    tools.repo.index = SearchIndex(tools.repo.parts)
    yield
