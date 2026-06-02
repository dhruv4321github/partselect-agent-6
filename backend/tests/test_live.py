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


def test_live_off_by_default():
    from app.config import settings
    # Live fetch defaults OFF (PartSelect blocks server-side requests; opt in
    # with curl_cffi + LIVE_FETCH=true). The demo runs on the curated catalog.
    assert settings.live_fetch is False


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


def test_repo_live_compatibility_unlisted_is_unconfirmed():
    """A part missing from a (partial) live list must NOT be asserted as a hard no."""
    repo = PartsRepository(persist=False)
    repo.load_sample()  # so PS11752778 resolves locally
    repo.live = _client_with_fixture(MODEL_HTML)
    comp = repo.check_compatibility("PS11752778", "WDF330PAHS")
    assert comp["compatible"] is None  # unconfirmed, not False


def test_seeded_path_unaffected_by_live():
    repo = PartsRepository(persist=False)
    repo.load_sample()
    repo.live = _client_with_fixture(MODEL_HTML)
    # Seeded incompatibility still authoritative + still offers an alternative.
    comp = repo.check_compatibility("PS11752778", "WDT780SAEM1")
    assert comp["compatible"] is False
    assert comp.get("alternative")


PART_HTML = b"""
<html><body>
<h1>Dishwasher Mounting Bracket</h1>
Manufacturer Part Number WP8269145
<span itemprop="price">$14.65</span>
<div>Add to Cart In Stock</div>
<div>Installation Instructions
  Door spring link broken
  1. Open the dishwasher and remove the two grommets. 2. Remove the kick plate under the door. 3. Pull the dishwasher out about 12 inches. 4. Attach the bracket and reverse to reinstall.
  Parts Used:
  Difficulty Level: Easy
  Total Repair Time: 15 - 30 mins
  Tools: Screw drivers, Wrench (Adjustable) https://www.youtube.com/watch?v=dTsA3uWROA0
</div>
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
    assert len(install["steps"]) == 4  # the four numbered steps
