# Catalog ingestion (`scrape_partselect.py`)

This is the **ingest** half of the scalability story in the main README. The agent
reads its catalog through `PartsRepository`, which today loads a small *seeded*
`data/parts.json`. This script produces that same file from the **live PartSelect
catalog**, so moving from demo data to the real catalog is a data-source swap with
no changes to the agent, tools, or frontend.

## How we get the data (verified June 2026)

- **No public PartSelect API.** There's no developer/partner API exposed publicly,
  so the realistic non-partnership route is crawling. (In a real engagement, ask
  PartSelect/Eldis for a direct data feed — cleaner than scraping and always fresh.)
- **`robots.txt` allows what we need.** Part detail pages (`/PS…htm`) and the
  category listing pages are crawlable. The search/facet endpoints, cart/checkout,
  account, and schematic paths are disallowed — this script never touches them and
  re-checks every URL against `robots.txt` at runtime via `urllib.robotparser`.
- **A master sitemap is the discovery mechanism.** `robots.txt` points to
  `…/PartSelect.com_Sitemap_Master.xml`, which indexes gzipped child sitemaps:
  ~100k–150k part pages (all appliances), ~400k model pages, plus repairs and
  categories. Sitemaps exist for exactly this purpose, so it's the polite,
  server-friendly way to enumerate the catalog.

## Two discovery modes

- **Scoped (default):** start from the Refrigerator-Parts and Dishwasher-Parts
  category trees and collect only those PS numbers — keeps the crawl within the
  case study's scope.
- **Full (`--full`):** enumerate every part URL from the sitemap, then filter by
  `appliance_type` after parsing. Use this when widening scope.

## Responsible use

- Set `CONTACT` at the top of the script (it goes into the User-Agent).
- Requests are rate-limited (`--delay`, default 1.5s) and back off on 429/503.
- Fetched HTML is cached to `.cache/` so re-runs don't re-hit the site.
- Review PartSelect's Terms of Service before a full crawl and keep volume modest.

## Usage

```bash
pip install requests beautifulsoup4 lxml

# Test on a handful first and eyeball the output:
python scrape_partselect.py --limit 5 --debug

# Scoped crawl → writes data/parts.scraped.json:
python scrape_partselect.py --appliance refrigerator dishwasher --delay 2.0

# Promote it once you've validated:
mv ../data/parts.scraped.json ../data/parts.json
```

## A note on selectors

`parse_part_page()` targets PartSelect's current HTML (schema.org `itemprop`
attributes, the "Fixes these symptoms" / "works with the following products"
sections, breadcrumbs). The selectors are isolated in small helpers because they're
the piece most likely to drift if PartSelect changes their markup — re-point them
there if a future run comes back sparse. The parser is verified against a fixture in
the same shape as the live page; run with `--limit 5 --debug` after any site change.

## Beyond parts

The same pattern extends to the other data files: the **Models** sitemaps populate
real compatibility (`models.json`), and the **Repairs** sitemap populates symptom
guides (`repair_help.json`). At catalog scale you'd then embed parts into a vector
DB behind the `SearchIndex` interface for semantic search — the second half of the
scalability story.
