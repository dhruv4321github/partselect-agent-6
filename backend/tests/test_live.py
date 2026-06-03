"""Offline tests for the hybrid live-fetch layer.

These never touch the network: they enable the client and stub its `_get` with
fixture HTML shaped like real PartSelect model/part pages. They prove the parser
and the repository fallback work independently of the live site (whose markup can
drift) and that the seeded path is unaffected.
"""
from app.catalog import PartsRepository
from app.live import PartSelectClient

MODEL_HTML = b"""
<html><body>
<h1>WDF330PAHS Whirlpool Dishwasher - Overview</h1>
<a href="/PS11753379-Whirlpool-WPW10348269-Dishwasher-Drain-Pump.htm">Dishwasher Drain Pump</a>
<span>(65)</span> Manufacturer #: WPW10348269 $61.15 In Stock
[{"position":0,"name":"Home"},{"position":1,"name":"Dishwasher"},{"position":2,"name":"Whirlpool"},{"position":3,"name":"WDF330PAHS"}]
</body></html>
"""


def _client_with_fixture(html):
    c = PartSelectClient(enabled=False)  # skip network robots read
    c.enabled = True
    c._ensure_robots = lambda: True       # no network
    c._get = lambda url, binary=False: html
    c._resolve_short = lambda ps: None    # no network resolution in tests
    return c


def test_live_model_parser():
    c = _client_with_fixture(MODEL_HTML)
    res = c.fetch_model("WDF330PAHS")
    assert res and res["model"]["brand"] == "Whirlpool"
    assert res["model"]["appliance_type"] == "Dishwasher"
    assert res["parts"][0]["ps_number"] == "PS11753379"
    assert res["parts"][0]["price"] == 61.15


def test_repo_live_model_fallback():
    repo = PartsRepository(persist=False)
    repo.live = _client_with_fixture(MODEL_HTML)
    # Not in the (empty) cache -> resolved live.
    m = repo.get_model("WDF330PAHS")
    assert m and m.get("source") == "live"
    pf = repo.parts_for_model("WDF330PAHS")
    assert pf["status"] == "ok" and len(pf["parts"]) == 1


def test_repo_live_compatibility_listed_part():
    repo = PartsRepository(persist=False)
    repo.live = _client_with_fixture(MODEL_HTML)
    comp = repo.check_compatibility("PS11753379", "WDF330PAHS")
    assert comp["compatible"] is True


def _seed_part(repo):
    """Seed a known part into the repo for offline compatibility tests."""
    from tests.conftest import FIXTURE_PART
    repo.parts = [FIXTURE_PART]
    repo._by_ps = {FIXTURE_PART["ps_number"].upper(): FIXTURE_PART}
    repo._by_mfr = {FIXTURE_PART["mfr_number"].upper(): FIXTURE_PART}
    repo._by_replaces = {rp.strip().upper(): FIXTURE_PART
                         for rp in FIXTURE_PART.get("replaces_parts", [])}


def test_repo_live_compatibility_unlisted_is_unconfirmed():
    """A part missing from a (partial) live list must NOT be asserted as a hard no."""
    repo = PartsRepository(persist=False)
    _seed_part(repo)
    repo.live = _client_with_fixture(MODEL_HTML)
    comp = repo.check_compatibility("PS11752778", "WDF330PAHS")
    assert comp["compatible"] is None  # unconfirmed, not False


PART_HTML = b"""
<html><body>
<h1>Dishwasher Mounting Bracket</h1>
Manufacturer Part Number WP8269145
<span itemprop="price">$14.65</span>
<div>Add to Cart In Stock</div>
<div class="repair-story">
  <div class="repair-story__details">
    Difficulty Level: Easy
    Total Repair Time: 15 - 30 mins
    Tools: Screw drivers, Wrench (Adjustable)
  </div>
  <div class="repair-story__title">Door spring link broken</div>
  <div class="repair-story__instruction">Open the dishwasher and remove the two grommets then remove the kick plate under the door.</div>
</div>
<div class="repair-story">
  <div class="repair-story__title">Bracket was cracked</div>
  <div class="repair-story__instruction">Pull the dishwasher out about 12 inches and attach the bracket.</div>
</div>
<img src="https://img.youtube.com/vi/dTsA3uWROA0/hqdefault.jpg" />
</body></html>
"""


def test_live_part_parser_extracts_install_steps():
    c = _client_with_fixture(PART_HTML)
    part = c.fetch_part("PS11745496", url="https://www.partselect.com/PS11745496-x.htm")
    install = part["install"]
    assert install["difficulty"] == "Easy"
    assert install["time_estimate"] == "15 - 30 mins"
    assert "Screw drivers" in install["tools_required"]
    assert install["video_url"].endswith("dTsA3uWROA0")
    assert len(install["steps"]) == 2


def test_repo_lookup_by_replaces_part():
    """A part can be found by one of its replaces_parts numbers."""
    repo = PartsRepository(persist=False)
    _seed_part(repo)
    found = repo.get_part("AP6019471")
    assert found is not None
    assert found["ps_number"] == "PS11752778"
