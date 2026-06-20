# Data Provenance & Methodology

This document records **where every field comes from** and **flags every proxy,
estimate, and known limitation**. The guiding principle is honesty over the
appearance of precision: real data where possible, clearly labeled
proxies/estimates otherwise, and never a fabricated number.

## Sources

| # | Source | Access | Provides |
|---|--------|--------|----------|
| 1 | Basketball-Reference **draft pages** (`/draft/NBA_{year}.html`) | Throttled scrape, cached | pick #, player, drafting team, college label, and **pre-aggregated career outcomes** (seasons, G, WS, WS/48, BPM, VORP) |
| 2 | Basketball-Reference **player pages** (`/players/{x}/{id}.html`) | Throttled scrape, cached | birthdate (for exact age at draft — top-20 picks only) |
| 3 | Basketball-Reference **awards** (`/awards/all_league.html`, `/awards/all_star_by_player.html`) | Throttled scrape, cached | All-NBA + All-Star selection counts, joined by BBRef player id |
| 4 | Sports-Reference **College Basketball** (`/cbb/players/{slug}.html`) | Throttled scrape, cached | final pre-draft college season: production + advanced (PER, TS%, USG%, WS/40, OBPM/DBPM/BPM), plus meta (listed ht/wt, position, RSCI rank) |
| 5 | **NBA Stats API** via `nba_api` (`draftcombineplayeranthro`, `draftcombinedrillresults`) | API, cached JSON | combine measurements: height w/ & w/o shoes, weight, wingspan, standing reach, body fat, hand size; max & standing vertical, lane agility, 3/4 sprint |

**Two pipeline modes** (`scripts/run_pipeline.py`):
- **live** — throttled (~18 req/min, under the ~20/min ceiling), every page/call
  cached to `data/raw_cache/` so each is fetched **at most once**; 404s are
  remembered so CBB slug-probing never re-hits known-missing pages.
- **fallback** (`--fallback`) — reads the committed `data/prospects.csv` only; no
  network. Guarantees the app runs in network-restricted environments.

Running the live scrape once populates the committed CSV.

## Field-by-field provenance

| Field(s) | Source | Notes / flags |
|----------|--------|---------------|
| `pick_overall`, `drafted_by`, `player`, `bbref_id`, `college_name` | 1 | — |
| `career_games`, `career_ws`, `ws_per_48`, `career_bpm`, `vorp`, `years_in_league` | 1 | Realized NBA career, current as of scrape date. |
| `all_star_count`, `all_nba_count` | 3 | Joined by `bbref_id`. 0 = no selection (correct for established careers; expected for provisional ones). |
| `outcome_tier` | derived | **Documented heuristic** (see below). Not ground truth. |
| `outcome_provisional` | derived | `True` when `draft_year > current_year − 7` — truncated career, tier not yet meaningful. |
| `pts`,`reb`,`ast`,`stl`,`blk`,`tov`,`fg_pct`,`fg3_pct`,`ft_pct`,`efg_pct`,`college_mpg`,`college_games` | 4 | `players_per_game` table, **final pre-draft season** (the one ending in the draft year; one-and-done → their only season). |
| `ts_pct`,`usg_pct`,`ast_pct`,`reb_pct`,`per`,`college_ws`,`ws_per_40`,`obpm`,`dbpm`,`college_bpm` | 4 | `players_advanced` table, same season. |
| `school`,`conference`,`class`,`position`,`rsci_rank`,`height_in_listed`,`weight_lb_listed`,`college_season` | 4 | `class` (FR/SO/JR/SR) is a free experience/youth signal. `height_in_listed` is **listed** (less reliable than combine-measured). |
| `height_wo_shoes_in`,`height_w_shoes_in`,`weight_lb`,`wingspan_in`,`standing_reach_in`,`max_vertical_in`,`no_step_vertical_in`,`lane_agility_s`,`three_quarter_sprint_s`,`body_fat_pct`,`hand_length_in`,`hand_width_in` | 5 | **Missing = NaN, never 0.** Stars routinely skip drills (e.g., RJ Barrett measured nothing in 2019). |
| `age_at_draft`, `age_source` | 2 / derived | **Hybrid**: exact DOB-derived age (`age_source="reported"`) for **top-20 picks**; class-based estimate (`"class_estimate"`, FR≈19.2 → SR≈22.2) for everyone else. 2026 prospects use real reported ages. |
| `mock_rank`,`bigboard_rank`,`mock_low`,`mock_high` | curated | **PROXY.** Null for the historical universe — **draft pick # is the historical consensus proxy** (the market's final aggregated verdict). A sparse, hand-curated mock/big-board overlay is added only for the 2026 prospects and notable recent years. Not a raw scouting grade. |
| `college_url` | 4 | Traceability — the exact CBB page used. |
| `data_flags` | derived | Free-text per-row caveats where applicable. |

## Derived: `outcome_tier` heuristic

A coarse label for the comparable model's base-rate estimation, defined in
`engine/schema.py` (single source of truth):

- **superstar** — All-NBA ≥ 1, or career WS ≥ 80, or VORP ≥ 25
- **all_star** — All-Star ≥ 1, or career WS ≥ 45, or VORP ≥ 12
- **starter** — WS ≥ 22, or VORP ≥ 4, or (≥ 6 seasons and WS/48 ≥ .08)
- **role_player** — ≥ 150 career games, or ≥ 4 seasons, or WS ≥ 4
- **bust** — otherwise (incl. never played)

Rationale: cumulative value (WS, VORP) separates stars from busts well; a rate
gate (WS/48) and accolades refine the top. This conflates longevity with quality
by design — it is a label, not a rating. Thresholds are tunable.

## Identity resolution (the hard part)

- **College ↔ NBA join** uses name-normalized slug probing on the CBB site,
  **verified** against each candidate page's own "Draft:" line (draft year +
  overall pick — a strong disambiguator for same-name players) or a school match.
- On a slug miss, a **Sports-Reference search fallback** resolves nickname/
  legal-name mismatches (e.g., "Ja Morant" → `temetrius-morant-1`).
- Combine ↔ draft join is fuzzy (`rapidfuzz` token-sort, threshold 88), scoped
  within the same draft year.
- **Every unverified college join is logged to `data/unmatched_report.csv`** for
  human review — never silently guessed or dropped.

## `level` classification (heuristic)

`NCAA` (college page resolved) · `non-NCAA` (no college label → international /
G-League / prep, college stats legitimately null) · `unresolved` (had a college
label we could not verify → in the unmatched report).

## 2026 prospects (Dybantsa, Peterson, Boozer)

Flagged **"current reported."** Final 2025–26 college stats from source 4 (the
season is complete by the June 2026 draft). Measurements and **consensus mock/
big-board rank from current draft coverage** — curated, cited, and flagged; some
measurements are reported (recruiting/coverage) rather than official combine.

## Known limitations

1. Combine attendance is voluntary and incomplete — expect gaps, especially for
   top prospects. We never impute zeros.
2. Outcome tiers for **2020+ classes are provisional** (careers in progress).
3. `mock_rank` history is intentionally sparse; we lean on pick # rather than
   fabricate a historical scouting dataset that does not exist publicly.
4. Listed heights/weights (CBB) are self/school-reported; prefer combine-measured
   fields where present.
5. Age is exact only for top-20 picks; class-estimated otherwise.

## Reproducibility

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/run_pipeline.py --years 2015-2024   # validate slice
.venv/bin/python scripts/run_pipeline.py --years 2000-2024   # full universe
.venv/bin/python scripts/run_pipeline.py --fallback          # offline, committed CSV
```

_Coverage stats (rows, NCAA-resolved %, combine %, unmatched count) are appended
after the full build completes._
