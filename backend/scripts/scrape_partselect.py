#!/usr/bin/env python3
"""
scrape_partselect.py — ingestion layer for the parts catalog.

This is the production implementation of the "ingest" half of the data story:
it discovers Refrigerator/Dishwasher part pages on PartSelect, fetches them
politely, parses each into the SAME dict shape as backend/data/parts.json, and
writes a catalog file. Nothing downstream changes — PartsRepository reads the
output exactly as it reads the seeded sample today.

WHY THIS DESIGN (verified against the live site, 2026-06):
  • No public PartSelect API exists, so discovery is via their sitemap, which is
    the robots-compliant, server-friendly way to enumerate a site.
  • robots.txt ALLOWS /PS…htm part pages and the category listing pages, but
    DISALLOWS the search/facet endpoints (/search/, /facetsearch/,
    /PartSearchResults.aspx, …) and all cart/checkout/account pages. This script
    never touches a disallowed path, and it re-checks every URL against
    robots.txt at runtime.
  • The master sitemap (…/PartSelect.com_Sitemap_Master.xml) indexes ~100k–150k
    part pages across ALL appliances. We scope to fridge + dishwasher by starting
    from the two category trees rather than ingesting the whole universe.

RESPONSIBLE USE:
  • Identifies itself with a real User-Agent and a contact string — set CONTACT.
  • Rate-limits every request (--delay, default 1.5s) and backs off on errors.
  • Caches fetched HTML to disk so re-runs don't re-hit the site.
  • Respects robots.txt via urllib.robotparser. If a path is disallowed, it skips.
  • You are responsible for reviewing PartSelect's Terms of Service before running
    a full crawl, and for keeping request volume considerate. For production, a
    direct data feed / partnership with PartSelect is preferable to crawling.

USAGE:
  pip install requests beautifulsoup4 lxml
  python scrape_partselect.py --appliance refrigerator dishwasher --limit 50
  python scrape_partselect.py --full --delay 2.0 --out ../data/parts.json

NOTE ON SELECTORS:
  The parse_part_page() selectors are written against PartSelect's current page
  structure but are the part most likely to drift when they change their HTML.
  They are isolated in clearly-marked helpers so they're cheap to re-point. Run
  with --limit 5 --debug first and eyeball the output before a full crawl.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.robotparser
from dataclasses import dataclass, field, asdict
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── Configuration ─────────────────────────────────────────────────────
BASE = "https://www.partselect.com"
SITEMAP_MASTER = f"{BASE}/sitemaps/PartSelect.com_Sitemap_Master.xml"
CONTACT = "your-email@example.com"  # ← set this; it goes in the User-Agent
USER_AGENT = f"PartSelectCatalogBot/1.0 (+contact: {CONTACT})"

# Category landing pages used to SCOPE the crawl to the two in-scope appliances.
CATEGORY_ROOTS = {
    "refrigerator": f"{BASE}/Refrigerator-Parts.htm",
    "dishwasher": f"{BASE}/Dishwasher-Parts.htm",
}

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
PS_RE = re.compile(r"/(PS\d+)-", re.IGNORECASE)


# ── Catalog record — mirrors backend/data/parts.json exactly ──────────
@dataclass
class Part:
    ps_number: str
    mfr_number: str = ""
    name: str = ""
    brand: str = ""
    appliance_type: str = ""
    category: str = ""
    price: float = 0.0
    in_stock: bool = True
    rating: Optional[float] = None
    review_count: int = 0
    image_url: str = ""
    url: str = ""
    description: str = ""
    symptoms_fixed: list = field(default_factory=list)
    compatible_brands: list = field(default_factory=list)
    compatible_models: list = field(default_factory=list)
    replaces_parts: list = field(default_factory=list)
    install: dict = field(default_factory=dict)
    verified: bool = True  # scraped from the live listing


# ── Polite HTTP layer ─────────────────────────────────────────────────
class Fetcher:
    """Rate-limited, cached, robots-aware GET."""

    def __init__(self, delay: float = 1.5, debug: bool = False):
        self.delay = delay
        self.debug = debug
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last = 0.0
        os.makedirs(CACHE_DIR, exist_ok=True)

        # Load and parse robots.txt once.
        self.robots = urllib.robotparser.RobotFileParser()
        self.robots.set_url(f"{BASE}/robots.txt")
        try:
            self.robots.read()
        except Exception as e:  # pragma: no cover
            print(f"! could not read robots.txt ({e}); aborting to be safe")
            raise

    def allowed(self, url: str) -> bool:
        return self.robots.can_fetch(USER_AGENT, url)

    def _cache_path(self, url: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", urlparse(url).path)[:180]
        return os.path.join(CACHE_DIR, safe + ".html")

    def get(self, url: str, binary: bool = False) -> Optional[bytes]:
        if not self.allowed(url):
            if self.debug:
                print(f"  · skip (robots-disallowed): {url}")
            return None

        cache = self._cache_path(url)
        if not binary and os.path.exists(cache):
            with open(cache, "rb") as f:
                return f.read()

        # Throttle.
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)

        for attempt in range(3):
            try:
                r = self.session.get(url, timeout=30)
                self._last = time.time()
                if r.status_code == 200:
                    if not binary:
                        with open(cache, "wb") as f:
                            f.write(r.content)
                    return r.content
                if r.status_code in (429, 503):  # back off and retry
                    time.sleep(self.delay * (attempt + 2))
                    continue
                if self.debug:
                    print(f"  · HTTP {r.status_code}: {url}")
                return None
            except requests.RequestException as e:
                if self.debug:
                    print(f"  · error ({e}); retrying")
                time.sleep(self.delay * (attempt + 2))
        return None


# ── Discovery ─────────────────────────────────────────────────────────
def discover_from_category(fetcher: Fetcher, root_url: str, debug=False) -> set[str]:
    """Walk a category landing page (and its paginated part lists) and collect
    every PS part-page URL found. Category pages are robots-allowed."""
    seen_part_urls: set[str] = set()
    to_visit, visited = [root_url], set()

    while to_visit:
        url = to_visit.pop()
        if url in visited:
            continue
        visited.add(url)
        html = fetcher.get(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")

        for a in soup.find_all("a", href=True):
            href = urljoin(BASE, a["href"])
            if PS_RE.search(href):
                seen_part_urls.add(href.split("?")[0])
            # Follow same-category sub-pages / pagination, but never search paths.
            elif _is_followable_category_link(href, root_url) and href not in visited:
                to_visit.append(href)

        if debug:
            print(f"  · {url} → {len(seen_part_urls)} parts so far")

    return seen_part_urls


def _is_followable_category_link(href: str, root_url: str) -> bool:
    p = urlparse(href).path.lower()
    if not href.startswith(BASE):
        return False
    if any(bad in p for bad in ("/search", "/facetsearch", "/user", "/cart", "/secure")):
        return False
    # Stay within parts listing pages (heuristic: *-Parts.htm or paginated listings).
    return p.endswith("-parts.htm") or "/parts/" in p


def discover_from_sitemap(fetcher: Fetcher, debug=False) -> Iterable[str]:
    """Yield ALL part-detail URLs from the gzipped PartDetail sitemaps. Use this
    for the full universe (all appliances); scope afterward by appliance_type."""
    master = fetcher.get(SITEMAP_MASTER)
    if not master:
        return
    child_locs = re.findall(rb"<loc>(.*?PartDetail.*?)</loc>", master)
    for loc in child_locs:
        loc = loc.decode()
        blob = fetcher.get(loc, binary=True)
        if not blob:
            continue
        xml = gzip.decompress(blob) if loc.endswith(".gz") else blob
        for m in re.finditer(rb"<loc>(.*?)</loc>", xml):
            url = m.group(1).decode()
            if PS_RE.search(url):
                yield url


# ── Parsing (the selector-dependent part) ─────────────────────────────
def parse_part_page(html: bytes, url: str) -> Optional[Part]:
    """Parse one part detail page into a Part. Selectors target PartSelect's
    current structure; validate with --limit 5 --debug before a full run."""
    soup = BeautifulSoup(html, "lxml")

    ps_match = PS_RE.search(url)
    if not ps_match:
        return None
    part = Part(ps_number=ps_match.group(1).upper(), url=url.split("?")[0])

    # Name (page H1).
    h1 = soup.find("h1")
    if h1:
        part.name = _clean(h1.get_text())

    # Manufacturer number, price, rating, etc. PartSelect exposes these as
    # labelled spans / itemprops; we read a few resilient signals.
    text = soup.get_text(" ", strip=True)

    mfr = re.search(r"Manufacturer Part Number\s*([A-Z0-9]+)", text)
    if mfr:
        part.mfr_number = mfr.group(1)

    price = soup.find(attrs={"itemprop": "price"}) or soup.find(class_=re.compile("price", re.I))
    if price:
        m = re.search(r"\d+(?:\.\d{2})?", price.get_text())
        if m:
            part.price = float(m.group())

    rating = soup.find(attrs={"itemprop": "ratingValue"})
    if rating:
        try:
            part.rating = float(rating.get_text(strip=True))
        except ValueError:
            pass
    rc = soup.find(attrs={"itemprop": "reviewCount"})
    if rc:
        part.review_count = int(re.sub(r"\D", "", rc.get_text()) or 0)

    part.in_stock = "in stock" in text.lower() or "add to cart" in text.lower()

    img = soup.find("img", attrs={"itemprop": "image"}) or soup.find("img", src=re.compile("/parts/", re.I))
    if img and img.get("src"):
        part.image_url = urljoin(BASE, img["src"])

    # "Fixes these symptoms" list.
    part.symptoms_fixed = _list_after_label(soup, "Fixes these symptoms") or \
        _list_after_label(soup, "fixes the following symptoms")

    # "This part works with the following products" → brands.
    brands = _list_after_label(soup, "works with the following products")
    part.compatible_brands = [b for b in brands if b and b[0].isupper()][:12]

    # "Replaces these parts" / "Part# replaces".
    repl = re.search(r"replaces?[^A-Za-z0-9]+([A-Z0-9,\s]+)", text)
    if repl:
        part.replaces_parts = [x.strip() for x in repl.group(1).split(",") if x.strip()][:30]

    # Appliance type + category (from breadcrumb).
    crumb = [a.get_text(strip=True) for a in soup.select("nav a, .breadcrumb a")]
    for c in crumb:
        if c in ("Refrigerator", "Dishwasher"):
            part.appliance_type = c
        elif c and c not in ("Home", "Parts") and not c.endswith("Parts"):
            part.category = c
    if not part.brand and part.compatible_brands:
        part.brand = part.compatible_brands[0]

    return part


def _list_after_label(soup: BeautifulSoup, label: str) -> list:
    """Find a section whose heading contains `label`, return its item texts."""
    node = soup.find(string=re.compile(re.escape(label), re.I))
    if not node:
        return []
    container = node.find_parent()
    items = []
    if container:
        sib = container.find_next(["ul", "div"])
        if sib:
            items = [_clean(li.get_text()) for li in sib.find_all(["li", "a"])]
    return [i for i in items if i][:20]


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


# ── Orchestration ─────────────────────────────────────────────────────
def run(appliances: list[str], limit: Optional[int], delay: float, out: str,
        full: bool, debug: bool):
    fetcher = Fetcher(delay=delay, debug=debug)

    # 1) Discover scoped part URLs.
    urls: set[str] = set()
    if full:
        print("Discovering ALL part URLs from sitemap (this is the full universe)…")
        for u in discover_from_sitemap(fetcher, debug):
            urls.add(u)
            if limit and len(urls) >= limit:
                break
    else:
        for appliance in appliances:
            root = CATEGORY_ROOTS.get(appliance)
            if not root:
                print(f"! unknown appliance '{appliance}', skipping")
                continue
            print(f"Discovering {appliance} parts from {root} …")
            found = discover_from_category(fetcher, root, debug)
            urls |= found
            print(f"  → {len(found)} {appliance} part URLs")
    if limit:
        urls = set(list(urls)[:limit])
    print(f"Discovered {len(urls)} part URLs to fetch.\n")

    # 2) Fetch + parse each.
    parts: list[dict] = []
    for i, url in enumerate(sorted(urls), 1):
        html = fetcher.get(url)
        if not html:
            continue
        try:
            part = parse_part_page(html, url)
        except Exception as e:  # keep going; one bad page shouldn't kill the run
            if debug:
                print(f"  · parse error on {url}: {e}")
            continue
        if part and part.name:
            parts.append(asdict(part))
        if debug or i % 25 == 0:
            print(f"  parsed {i}/{len(urls)}")

    # 3) Write the catalog in the exact shape PartsRepository expects.
    parts.sort(key=lambda p: p["ps_number"])
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump(parts, f, indent=2)
    print(f"\n✓ wrote {len(parts)} parts → {out}")
    print("  (drop-in for backend/data/parts.json — no other code changes needed)")


def main():
    ap = argparse.ArgumentParser(description="Scrape PartSelect fridge/dishwasher parts.")
    ap.add_argument("--appliance", nargs="+", default=["refrigerator", "dishwasher"],
                    choices=["refrigerator", "dishwasher"])
    ap.add_argument("--full", action="store_true",
                    help="Ingest ALL parts via sitemap instead of the two category trees.")
    ap.add_argument("--limit", type=int, default=None, help="Cap parts (for testing).")
    ap.add_argument("--delay", type=float, default=1.5, help="Seconds between requests.")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "data", "parts.scraped.json"))
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if CONTACT == "your-email@example.com":
        print("! Please set CONTACT at the top of this file before crawling.\n")
    run(args.appliance, args.limit, args.delay, args.out, args.full, args.debug)


if __name__ == "__main__":
    main()
