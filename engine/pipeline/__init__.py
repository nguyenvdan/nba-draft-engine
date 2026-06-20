"""Data-acquisition pipeline.

Two modes (see scripts/run_pipeline.py):
  - live   : throttled + locally cached fetch from Basketball-Reference,
             Sports-Reference CBB, and the NBA Stats API (nba_api).
  - fallback: read the committed data/prospects.csv (no network).

Every page is fetched at most once and cached under data/raw_cache/ so the
scrape is reproducible and polite (~18 req/min, under the ~20/min ceiling).
"""
