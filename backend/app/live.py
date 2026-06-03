"""PartSelectClient — the live half of the hybrid catalog.

When the seeded catalog doesn't have a part or model, the repository can fall
back to this client, which fetches the data straight from partselect.com, parses
it into the SAME dict shapes the rest of the app uses, and caches the result so
repeated/demo queries are instant.

Two retrieval paths, by reliability:
  • MODEL pages — `…/Models/{MODEL}/` is a deterministic URL built straight from
    the model number. One fetch returns the model identity plus the parts that
    fit it (PS#, mfr#, name, price, rating). This is the primary, high-value path
    and it works for ANY model, not just the seeded ones.
  • PART pages — `/PS…htm` slugs aren't derivable from a bare PS number, so a
    bare-PS lookup needs URL resolution. We resolve via (a) a URL we already
    learned (e.g. from a model page), or (b) the sitemap index — a one-time
    download of PartSelect's sitemap XML files that maps all ~100K PS numbers to
    their canonical URLs (cached to disk as ps_url_index.json). The sitemap path
    is the primary resolution mechanism; PartSelect returns HTTP 500 for short
    `/PSxxxxx.htm` URLs, so the short-URL redirect path is a non-functional
    fallback kept for robustness.

Politeness: identifies via User-Agent, rate-limits, caches pages to disk, and
checks robots.txt at runtime. The model OVERVIEW page is robots-allowed for all
agents. For production scale you'd prefer a data feed / periodic cached crawl
over per-request live hits — see README.

NOTE ON SELECTORS: the parsers target PartSelect's current markup and are the
piece most likely to drift if the site changes. They degrade gracefully (a
missing field becomes a default, not a crash) and are isolated below.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.robotparser
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup
    _DEPS = True
except Exception:  # requests/bs4 are only needed when live fetch is enabled
    _DEPS = False

# Optional accelerator: curl_cffi impersonates a real browser's TLS/HTTP2
# fingerprint, which gets past Akamai-style bot protection that returns 403 to
# plain `requests` regardless of headers. If installed, we use it; otherwise we
# fall back to requests (which works for non-protected hosts / fixtures).
try:
    from curl_cffi import requests as cffi_requests
    _HAS_CFFI = True
except Exception:
    cffi_requests = None
    _HAS_CFFI = False

BASE = "https://www.partselect.com"
SITEMAP_MASTER = f"{BASE}/sitemaps/PartSelect.com_Sitemap_Master.xml"
# PartSelect's CDN rejects unknown bot user-agents (returns non-200), so we send
# a normal browser UA. We still honor robots.txt (checked below) and rate-limit,
# which are the substantive politeness controls. For production-scale use a data
# feed / official crawler agreement instead of per-request live fetches.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
PS_URL_RE = re.compile(r"/(PS\d+)-[^\s\"'?]+\.htm", re.IGNORECASE)
PS_NUM_RE = re.compile(r"PS\d+", re.IGNORECASE)


def _log(msg: str):
    print(f"[live] {msg}", flush=True)


class PartSelectClient:
    def __init__(self, enabled=False, delay=1.5, cache_dir=".live_cache",
                 resolve_via_sitemap=False):
        self.enabled = enabled and _DEPS
        self.delay = delay
        self.cache_dir = cache_dir
        self.resolve_via_sitemap = resolve_via_sitemap
        self._last = 0.0
        self._ps_url_index: Optional[dict] = None  # lazily built
        self.robots = None                          # lazily loaded on first fetch
        if not self.enabled:
            return
        os.makedirs(self.cache_dir, exist_ok=True)
        self._headers = {
            "User-Agent": USER_AGENT,
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                       "image/avif,image/webp,*/*;q=0.8"),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        if _HAS_CFFI:
            # Impersonate Chrome's TLS fingerprint to get past Akamai-style 403s.
            self.session = cffi_requests.Session(impersonate="chrome")
            _log("using curl_cffi (browser impersonation) for live fetch")
        else:
            self.session = requests.Session()
        self.session.headers.update(self._headers)

    def _http_get(self, url: str, timeout: int = 30, allow_redirects: bool = True):
        """Single HTTP entry point so robots, pages, and resolution all benefit
        from browser impersonation when curl_cffi is installed."""
        return self.session.get(url, timeout=timeout, allow_redirects=allow_redirects)

    def _ensure_robots(self) -> bool:
        """Load robots.txt on first use (keeps construction / app startup
        network-free). Disables live fetch if robots.txt is unreachable."""
        if self.robots is not None:
            return self.enabled
        self.robots = urllib.robotparser.RobotFileParser()
        try:
            r = self._http_get(f"{BASE}/robots.txt", timeout=10)
            if r.status_code == 200:
                self.robots.parse(r.text.splitlines())
            else:
                _log(f"robots.txt returned HTTP {r.status_code}; live fetch disabled "
                     f"(install curl_cffi if this is a 403 — see README)")
                self.enabled = False
        except Exception as e:
            _log(f"robots.txt unreachable ({e}); live fetch disabled")
            self.enabled = False
        return self.enabled

    # ---- polite HTTP ---------------------------------------------------
    def _cache_path(self, url: str) -> str:
        h = hashlib.sha1(url.encode()).hexdigest()[:20]
        return os.path.join(self.cache_dir, f"{h}.html")

    def _get(self, url: str, binary=False) -> Optional[bytes]:
        if not self.enabled or not self._ensure_robots():
            return None
        if not self.robots.can_fetch(USER_AGENT, url):
            _log(f"robots.txt disallows: {url}")
            return None
        cache = self._cache_path(url)
        if not binary and os.path.exists(cache):
            with open(cache, "rb") as f:
                return f.read()
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = self._http_get(url, timeout=30)
            self._last = time.time()
            if r.status_code != 200:
                _log(f"HTTP {r.status_code} for {url}")
                return None
            if not binary:
                with open(cache, "wb") as f:
                    f.write(r.content)
            return r.content
        except Exception as e:
            _log(f"fetch error for {url}: {e}")
            return None

    # ---- public: model ------------------------------------------------
    def fetch_model(self, model_number: str) -> Optional[dict]:
        """Return {'model': <model dict>, 'parts': [<part dict>, ...]} or None.
        Model dict matches models.json; part dicts match parts.json."""
        if not self.enabled or not model_number:
            return None
        m = re.sub(r"\s+", "", model_number).upper()
        _log(f"fetching model {m} ...")
        html = self._get(f"{BASE}/Models/{m}/")
        if not html:
            return None
        parsed = self._parse_model_page(html, m)
        _log(f"model {m}: {'parsed ' + str(len(parsed['parts'])) + ' parts' if parsed else 'parse failed'}")
        return parsed

    # ---- public: part -------------------------------------------------
    def fetch_part(self, part_number: str, url: Optional[str] = None) -> Optional[dict]:
        """Fetch one part by PS number. `url` short-circuits resolution when the
        caller already knows the part page (e.g. learned from a model page)."""
        if not self.enabled or not part_number:
            return None
        ps = part_number.strip().upper()
        if not url:
            url = self._resolve_ps_url(ps)
        if not url:
            _log(f"could not resolve a URL for {ps}")
            return None
        _log(f"fetching part {ps} -> {url}")
        html = self._get(url)
        if not html:
            return None
        return self._parse_part_page(html, url, ps)

    # ---- PS -> URL resolution -----------------------------------------
    def _resolve_ps_url(self, ps: str) -> Optional[str]:
        # 1) Try short URL redirect (currently returns 500 on PartSelect, but
        #    kept as a first attempt in case they restore it).
        short = self._resolve_short(ps)
        if short:
            return short
        # 2) Primary path: the sitemap index (~100K PS# -> URL mappings, cached).
        if not self.resolve_via_sitemap:
            return None
        if self._ps_url_index is None:
            self._ps_url_index = self._build_ps_url_index()
        return self._ps_url_index.get(ps.upper())

    def _resolve_short(self, ps: str) -> Optional[str]:
        """Try /PSxxxxx.htm and follow redirects to the canonical part URL."""
        if not self._ensure_robots():
            return None
        url = f"{BASE}/{ps}.htm"
        if not self.robots.can_fetch(USER_AGENT, url):
            return None
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = self._http_get(url, timeout=30, allow_redirects=True)
            self._last = time.time()
            if r.status_code == 200 and PS_URL_RE.search(r.url):
                # Cache the resolved page body so the follow-up _get is free.
                try:
                    with open(self._cache_path(r.url.split("?")[0]), "wb") as f:
                        f.write(r.content)
                except Exception:
                    pass
                return r.url.split("?")[0]
        except Exception as e:
            _log(f"short-URL resolve failed for {ps}: {e}")
        return None

    def _build_ps_url_index(self) -> dict:
        """Download the part-detail sitemaps and map PS# -> URL (~100K entries).
        Cached to disk as ps_url_index.json; one-time multi-MB download."""
        idx_path = os.path.join(self.cache_dir, "ps_url_index.json")
        if os.path.exists(idx_path):
            with open(idx_path) as f:
                return json.load(f)
        _log("building PartSelect part-URL index from sitemap "
             "(one-time, ~10-30s; cached afterwards)...")
        index: dict = {}
        master = self._get(SITEMAP_MASTER)
        if master:
            for loc in re.findall(rb"<loc>(.*?PartDetail.*?)</loc>", master):
                blob = self._get(loc.decode(), binary=True)
                if not blob:
                    continue
                xml = gzip.decompress(blob) if loc.endswith(b".gz") else blob
                for u in re.findall(rb"<loc>(.*?)</loc>", xml):
                    u = u.decode()
                    mt = PS_URL_RE.search(u)
                    if mt:
                        index[mt.group(1).upper()] = u
        with open(idx_path, "w") as f:
            json.dump(index, f)
        return index

    # ---- parsers (selector-dependent; degrade gracefully) -------------
    def _parse_model_page(self, html: bytes, model_number: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Brand + appliance type from the JSON breadcrumb at the foot of the page,
        # falling back to the H1 ("WDT780SAEM1 Whirlpool Dishwasher - Overview").
        brand, appliance = self._model_identity(html, soup)

        # Collect parts from structured listing cards (mega-m__part containers),
        # falling back to anchor-walking for pages that don't use that layout.
        parts, seen = [], set()
        for card in soup.find_all(class_="mega-m__part"):
            a = card.find("a", href=PS_URL_RE)
            if not a:
                continue
            ps = PS_URL_RE.search(a["href"]).group(1).upper()
            if ps in seen:
                continue
            seen.add(ps)
            url = a["href"].split("?")[0]
            if url.startswith("/"):
                url = BASE + url
            parts.append(self._part_from_card(card, ps, url, brand, appliance))

        if not parts:
            for a in soup.find_all("a", href=True):
                mt = PS_URL_RE.search(a["href"])
                if not mt:
                    continue
                ps = mt.group(1).upper()
                if ps in seen:
                    continue
                seen.add(ps)
                url = a["href"].split("?")[0]
                if url.startswith("/"):
                    url = BASE + url
                block = self._block_text_for(a)
                parts.append(self._part_from_listing(ps, url, a.get_text(" ", strip=True),
                                                     block, brand, appliance))

        if not parts and "Overview" not in text:
            return None  # likely not a real model page

        model = {
            "model_number": model_number,
            "brand": brand,
            "appliance_type": appliance,
            "compatible_parts": [p["ps_number"] for p in parts],
            "verified": True,
            "source": "live",
        }
        return {"model": model, "parts": parts}

    def _model_identity(self, html: bytes, soup) -> tuple[str, str]:
        brand, appliance = "", ""
        # Breadcrumb JSON: [{"name":"Home"},{"name":"Dishwasher"},{"name":"Whirlpool"},...]
        mt = re.search(rb'\[\{"position":0,"name":"Home".*?\}\]', html)
        if mt:
            try:
                crumb = json.loads(mt.group(0).decode())
                names = [c.get("name", "") for c in crumb]
                for n in names:
                    if n in ("Dishwasher", "Refrigerator"):
                        appliance = n
                # brand is usually the crumb between appliance and model
                if len(names) >= 3:
                    brand = names[2]
            except Exception:
                pass
        if not appliance or not brand:
            h1 = soup.find("h1")
            if h1:
                words = h1.get_text(" ", strip=True).split()
                for w in words:
                    if w in ("Dishwasher", "Refrigerator"):
                        appliance = appliance or w
                if len(words) >= 2:
                    brand = brand or words[1]
        return brand, appliance

    def _part_from_listing(self, ps, url, name, block, brand, appliance) -> dict:
        mfr = ""
        mt = re.search(r"Manufacturer\s*#?:?\s*([A-Z0-9]+)", block)
        if mt:
            mfr = mt.group(1)
        price = 0.0
        pm = re.search(r"\$(\d+(?:\.\d{2})?)", block)
        if pm:
            price = float(pm.group(1))
        rating, reviews = None, 0
        rm = re.search(r"\((\d+)\)", block)
        if rm:
            reviews = int(rm.group(1))
        clean_name = _clean(name)
        if not clean_name or clean_name.lower() == "part":
            clean_name = _name_from_url(url) or clean_name or "Part"
        return self._part_dict(
            ps_number=ps, mfr_number=mfr, name=clean_name,
            brand=brand, appliance_type=appliance, price=price,
            in_stock="out of stock" not in block.lower(),
            rating=rating, review_count=reviews, url=url,
        )

    def _part_from_card(self, card, ps, url, brand, appliance) -> dict:
        """Extract rich part data from a mega-m__part container on model pages."""
        block = card.get_text(" ", strip=True)

        name = ""
        for link in card.find_all("a", href=PS_URL_RE):
            t = link.get_text(strip=True)
            if t and not t.startswith("★"):
                name = t
                break
        if not name:
            name = _name_from_url(url) or "Part"

        mfr = ""
        mt = re.search(r"Manufacturer\s*#?:?\s*([A-Z0-9]+)", block)
        if mt:
            mfr = mt.group(1)

        price = 0.0
        price_el = card.find(class_=re.compile(r"price"))
        if price_el:
            pm = re.search(r"(\d+(?:\.\d{2})?)", price_el.get_text())
            if pm:
                price = float(pm.group(1))

        reviews = 0
        rm = re.search(r"\((\d+)\)", block)
        if rm:
            reviews = int(rm.group(1))

        desc = ""
        dm = re.search(r"(This (?:OEM|authentic|replacement|is)\b.+?\.\.\.?|This (?:OEM|authentic|replacement|is)\b.+?\.)", block)
        if dm:
            desc = _clean(dm.group(0).rstrip("."))

        image_url = ""
        img = card.find("img")
        if img:
            image_url = img.get("data-src") or img.get("src") or ""
            if image_url.startswith("data:"):
                image_url = ""

        return self._part_dict(
            ps_number=ps, mfr_number=mfr, name=_clean(name),
            brand=brand, appliance_type=appliance, price=price,
            in_stock="out of stock" not in block.lower(),
            rating=None, review_count=reviews, url=url, description=desc,
            image_url=image_url,
        )

    def _parse_part_page(self, html: bytes, url: str, ps: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        h1 = soup.find("h1")
        name = _clean(h1.get_text()) if h1 else "Part"
        mfr = ""
        mt = re.search(r"Manufacturer Part Number\s*([A-Z0-9]+)", text)
        if mt:
            mfr = mt.group(1)

        price = _itemprop_val(soup, "price", as_float=True)
        if not price:
            price_el = soup.find(class_=re.compile(r"price"))
            if price_el:
                pm = re.search(r"(\d+(?:\.\d{2})?)", price_el.get_text())
                if pm:
                    price = float(pm.group(1))
        if not price:
            pm = re.search(r"\$(\d+(?:\.\d{2})?)", text[:3000])
            if pm:
                price = float(pm.group(1))

        rating = _itemprop_val(soup, "ratingValue", as_float=True)
        if not rating:
            rm = re.search(r"(\d+(?:\.\d+)?)\s*/\s*5(?:\.0)?", text[:5000])
            if rm:
                rating = float(rm.group(1))

        reviews = int(_itemprop_val(soup, "reviewCount", as_float=True) or 0)
        if not reviews:
            rm = re.search(r"(\d+)\s*Reviews", text[:5000])
            if rm:
                reviews = int(rm.group(1))

        avail = soup.find(attrs={"itemprop": "availability"})
        in_stock = True
        if avail:
            in_stock = "instock" in (avail.get("content", "") + avail.get_text()).lower()
        else:
            in_stock = "in stock" in text.lower() or "add to cart" in text.lower()

        brand_el = soup.find(attrs={"itemprop": "brand"})
        brand = _clean(brand_el.get_text()) if brand_el else ""

        img = soup.find("img", attrs={"itemprop": "image"})

        desc_el = soup.find(attrs={"itemprop": "description"})
        desc = _clean(desc_el.get_text()) if desc_el else ""
        if not desc:
            desc_meta = soup.find("meta", attrs={"name": "description"})
            if desc_meta and desc_meta.get("content"):
                desc = _clean(desc_meta["content"])

        symptoms = _list_after(soup, "Fixes these symptoms") or _list_after(soup, "fixes the following symptoms")

        appliance = ""
        bc = re.search(rb'\[\{"position":0,"name":"Home".*?\}\]', html)
        if bc:
            try:
                for c in json.loads(bc.group(0)):
                    if c.get("name") in ("Dishwasher", "Refrigerator"):
                        appliance = c["name"]
                        break
            except Exception:
                pass
        if not appliance:
            appliance = "Refrigerator" if "Refrigerator" in text[:4000] else (
                "Dishwasher" if "Dishwasher" in text[:4000] else "")

        replaces = []
        rp = re.search(r"replaces\s+these:?\s*(.+?)(?:Back to|$)", text, re.I)
        if rp:
            replaces = [_clean(p) for p in re.split(r"[,\s]+", rp.group(1))
                        if _clean(p) and re.match(r"[A-Z0-9]", _clean(p))]

        models = []
        seen_models = set()
        for a in soup.find_all("a", href=re.compile(r"/Models/", re.I)):
            mm = re.search(r"/Models/([^/?]+)", a["href"])
            if mm:
                mn = mm.group(1).upper()
                if mn not in seen_models:
                    seen_models.add(mn)
                    models.append(mn)

        compatible_products = []
        brands_section = soup.find(string=re.compile(r"works with the following products", re.I))
        if brands_section:
            p = brands_section.find_parent()
            if p:
                sib = p.find_next(["ul", "div"])
                if sib:
                    compatible_products = [_clean(li.get_text()) for li in sib.find_all(["li", "a"])
                                         if _clean(li.get_text()) and _clean(li.get_text())[0].isupper()][:12]

        install = self._extract_install(soup, html)
        return self._part_dict(
            ps_number=ps, mfr_number=mfr, name=name,
            brand=brand, appliance_type=appliance,
            price=price, in_stock=in_stock,
            rating=rating, review_count=reviews,
            image_url=img["src"] if img and img.get("src") else "",
            url=url.split("?")[0], description=desc,
            symptoms_fixed=symptoms, compatible_products=compatible_products,
            compatible_models=models[:50], replaces_parts=replaces,
            install=install,
        )

    @staticmethod
    def _extract_install(soup, html: bytes) -> dict:
        """Extract install info from structured .repair-story containers."""
        install: dict = {}
        text = soup.get_text(" ", strip=True)

        # Gather difficulty/time/tools from ALL repair story detail blocks,
        # not just the first — tools may appear in any story.
        stories = soup.find_all(class_="repair-story")
        for story in stories:
            details = story.find(class_="repair-story__details")
            if not details:
                continue
            dt = details.get_text(" ", strip=True)
            if not install.get("difficulty"):
                d = re.search(
                    r"Difficulty Level:\s*(Really Easy|Very Easy|A Bit Difficult|Very Difficult|Easy|Difficult|Medium|Hard)",
                    dt, re.I)
                if d:
                    install["difficulty"] = d.group(1).strip()
            if not install.get("time_estimate"):
                t = re.search(
                    r"Total Repair Time:\s*((?:Less than |More than )?[\d\s\-]*(?:mins?|minutes?|hours?|hrs?))",
                    dt, re.I)
                if t:
                    install["time_estimate"] = _clean(t.group(1))
            if not install.get("tools_required"):
                tl = re.search(r"Tools?:\s*(.+?)$", dt)
                if tl:
                    tools = [_clean(p) for p in tl.group(1).split(",")
                             if _clean(p) and _clean(p).lower() != "none" and len(_clean(p)) < 50]
                    if tools:
                        install["tools_required"] = tools[:6]

        if stories:
            steps = []
            for story in stories[:5]:
                title_el = story.find(class_="repair-story__title")
                instr_el = story.find(class_="repair-story__instruction")
                title = _clean(title_el.get_text()) if title_el else ""
                instr = _clean(instr_el.get_text()) if instr_el else ""
                if title and instr and len(instr) > 10:
                    steps.append(f"{title}: {instr}")
                elif instr and len(instr) > 10:
                    steps.append(instr)
            if steps:
                install["steps"] = steps

        # Fallback: extract from full-page text if repair-story containers
        # didn't yield results.
        if not install.get("difficulty"):
            d = re.search(
                r"Difficulty Level:\s*(Really Easy|Very Easy|A Bit Difficult|Very Difficult|Easy|Difficult|Medium|Hard)",
                text, re.I)
            if d:
                install["difficulty"] = d.group(1).strip()
        if not install.get("time_estimate"):
            t = re.search(
                r"Total Repair Time:\s*((?:Less than |More than )?[\d\s\-]*(?:mins?|minutes?|hours?|hrs?))",
                text, re.I)
            if t:
                install["time_estimate"] = _clean(t.group(1))
        if not install.get("tools_required"):
            tl = re.search(r"Tools?:\s*(.+?)(?:\s{2,}|\s+Was this|\s+\d+ of \d+|$)", text)
            if tl:
                tools = [_clean(p) for p in tl.group(1).split(",")
                         if _clean(p) and _clean(p).lower() != "none" and len(_clean(p)) < 50]
                if tools:
                    install["tools_required"] = tools[:6]

        v = re.search(rb"https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+", html)
        if v:
            install["video_url"] = v.group(0).decode()
        else:
            vt = re.search(rb"img\.youtube\.com/vi/([\w-]+)/", html)
            if vt:
                install["video_url"] = f"https://www.youtube.com/watch?v={vt.group(1).decode()}"

        return install

    # ---- public: repair symptoms --------------------------------------
    def fetch_repair_symptoms(self, appliance_type: str) -> list[dict]:
        """Fetch the symptom index for an appliance type from PartSelect's
        /Repair/Refrigerator/ or /Repair/Dishwasher/ pages.
        Returns [{"title": str, "description": str, "url": str}, ...]."""
        if not self.enabled:
            return []
        slug = appliance_type.strip().capitalize()
        if slug not in ("Refrigerator", "Dishwasher"):
            return []
        url = f"{BASE}/Repair/{slug}/"
        html = self._get(url)
        if not html:
            return []
        return self._parse_symptom_index(html)

    def fetch_symptom_detail(self, symptom_url: str) -> Optional[dict]:
        """Fetch a symptom detail page and return structured causes.
        Returns {"symptom": str, "causes": [{"title": str, "detail": str,
                 "category_url": str}, ...]} or None."""
        if not self.enabled or not symptom_url:
            return None
        if symptom_url.startswith("/"):
            symptom_url = BASE + symptom_url
        html = self._get(symptom_url)
        if not html:
            return None
        return self._parse_symptom_detail(html, symptom_url)

    def fetch_model_symptoms(self, model_number: str) -> list[dict]:
        """Fetch the symptom list for a specific model from its overview page.
        Returns [{"title": str, "url": str}, ...]."""
        if not self.enabled or not model_number:
            return []
        m = re.sub(r"\s+", "", model_number).upper()
        html = self._get(f"{BASE}/Models/{m}/")
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        results = []
        seen = set()
        for a in soup.find_all("a", href=lambda h: h and "/Symptoms/" in (h or "")):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            title = re.sub(r"Fixed by.*", "", text).strip()
            if not title or title in seen:
                continue
            seen.add(title)
            href = urllib.parse.quote(href, safe="/:?&#=@")
            if href.startswith("/"):
                href = BASE + href
            results.append({"title": title, "url": href})
        return results

    def fetch_model_symptom_parts(self, symptom_url: str) -> Optional[dict]:
        """Fetch a model-specific symptom page and return parts that fix it,
        with fix-percentage data.
        Returns {"symptom": str, "parts": [{"ps_number", "name", "mfr_number",
                 "price", "in_stock", "fix_pct", "url"}, ...]} or None."""
        if not self.enabled or not symptom_url:
            return None
        if symptom_url.startswith("/"):
            symptom_url = BASE + symptom_url
        html = self._get(symptom_url)
        if not html:
            return None
        return self._parse_model_symptom_page(html, symptom_url)

    @staticmethod
    def _parse_model_symptom_page(html: bytes, url: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        symptom_name = _clean(h1.get_text()) if h1 else ""

        parts = []
        for container in soup.find_all(class_="symptoms"):
            block = container.get_text(" ", strip=True)
            ps, name, part_url = "", "", ""
            for a in container.find_all("a", href=PS_URL_RE):
                t = a.get_text(strip=True)
                mt = PS_URL_RE.search(a["href"])
                if mt:
                    ps = mt.group(1).upper()
                    part_url = a["href"].split("?")[0]
                    if part_url.startswith("/"):
                        part_url = BASE + part_url
                    if t and not re.match(r"^[A-Z0-9]+$", t) and t != ps:
                        name = t
            if not ps:
                continue
            if not name:
                name = _name_from_url(part_url) or ps

            pct_match = re.search(r"(\d+)\s*%", block)
            fix_pct = int(pct_match.group(1)) if pct_match else 0

            price_match = re.search(r"\$\s*(\d+(?:\.\d{2})?)", block)
            price = float(price_match.group(1)) if price_match else 0.0

            mfr_match = re.search(r"Part Number:\s*(\S+)", block)
            mfr = mfr_match.group(1) if mfr_match else ""

            in_stock = "in stock" in block.lower()

            parts.append({
                "ps_number": ps, "name": name, "mfr_number": mfr,
                "price": price, "in_stock": in_stock,
                "fix_pct": fix_pct, "url": part_url,
            })

        if not parts:
            return None
        parts.sort(key=lambda p: p["fix_pct"], reverse=True)
        return {"symptom": symptom_name, "url": url, "parts": parts}

    @staticmethod
    def _parse_symptom_index(html: bytes) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        symptom_div = soup.find("div", class_="symptom-list")
        if not symptom_div:
            return []
        results = []
        for link in symptom_div.find_all("a", href=True):
            href = link.get("href", "")
            if "/Repair/" not in href:
                continue
            heading = link.find(["h3", "h4", "b", "strong"])
            title = _clean(heading.get_text()) if heading else ""
            if not title:
                continue
            p = link.find("p")
            desc = _clean(p.get_text()) if p else ""
            href = urllib.parse.quote(href, safe="/:?&#=@")
            results.append({"title": title, "description": desc, "url": href})
        return results

    @staticmethod
    def _parse_symptom_detail(html: bytes, url: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "html.parser")
        symptom_div = soup.find("div", class_="symptom-list")
        if not symptom_div:
            return None
        h1 = soup.find("h1")
        symptom_name = _clean(h1.get_text()) if h1 else ""

        causes = []
        for h2 in symptom_div.find_all("h2", class_="section-title"):
            title = _clean(h2.get_text())
            desc_div = h2.find_next_sibling("div", class_="symptom-list__desc")
            if not desc_div:
                continue
            cols = desc_div.find_all("div", class_="col-lg-6")
            detail = ""
            category_url = ""
            if cols:
                paragraphs = cols[0].find_all("p")
                detail = " ".join(_clean(p.get_text()) for p in paragraphs if _clean(p.get_text()))
                if len(cols) > 1:
                    cat_link = cols[1].find("a", href=lambda h: h and h.endswith(".htm"))
                    if cat_link:
                        category_url = cat_link["href"]
                        if category_url.startswith("/"):
                            category_url = BASE + category_url
            causes.append({
                "title": title,
                "detail": detail,
                "category_url": category_url,
            })
        if not causes:
            return None
        return {"symptom": symptom_name, "url": url, "causes": causes}

    @staticmethod
    def _block_text_for(anchor) -> str:
        """Text near a part anchor, used to scrape price/mfr from a listing."""
        parent = anchor
        for _ in range(3):
            if parent.parent:
                parent = parent.parent
        return parent.get_text(" ", strip=True) if parent else ""

    @staticmethod
    def _part_dict(**kw) -> dict:
        """Build a parts.json-shaped dict with safe defaults for every key the
        rest of the app reads (so to_product_card never KeyErrors)."""
        base = {
            "ps_number": "", "mfr_number": "", "name": "", "brand": "",
            "appliance_type": "", "category": "", "price": 0.0, "in_stock": True,
            "rating": None, "review_count": 0, "image_url": "", "url": "",
            "description": "", "symptoms_fixed": [], "compatible_products": [],
            "compatible_models": [], "replaces_parts": [], "install": {},
            "verified": True, "source": "live",
        }
        base.update(kw)
        return base


def _name_from_url(url: str) -> str:
    """Extract a human-readable part name from a PartSelect URL slug.
    e.g. '.../PS11756150-Whirlpool-WPW10546503-Dishwasher-Upper-Rack-Adjuster.htm'
    -> 'Dishwasher Upper Rack Adjuster'"""
    mt = PS_URL_RE.search(url or "")
    if not mt:
        return ""
    slug = mt.group(0).rsplit("/", 1)[-1]
    slug = re.sub(r"\.htm$", "", slug, flags=re.I)
    parts = slug.split("-")
    # Slug format: PS#-Brand-MfrNumber-Descriptive-Name-Words
    # Skip first 3 tokens (PS number, brand, mfr number), keep the rest.
    name_parts = parts[3:] if len(parts) > 3 else []
    return " ".join(name_parts) if name_parts else ""


def _itemprop_val(soup, prop: str, as_float: bool = False):
    """Read an itemprop value from either the content attr (meta tags) or text."""
    el = soup.find(attrs={"itemprop": prop})
    if not el:
        return 0.0 if as_float else ""
    val = el.get("content") or el.get_text(strip=True)
    if as_float:
        m = re.search(r"[\d.]+", val or "")
        return float(m.group()) if m else 0.0
    return _clean(val)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _list_after(soup, label: str) -> list:
    node = soup.find(string=re.compile(re.escape(label), re.I))
    if not node:
        return []
    container = node.find_parent()
    if not container:
        return []
    sib = container.find_next(["ul", "div"])
    if not sib:
        return []
    return [_clean(li.get_text()) for li in sib.find_all(["li", "a"]) if _clean(li.get_text())][:20]
