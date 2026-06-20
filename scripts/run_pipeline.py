"""Data-pipeline CLI.

  live scrape:   python scripts/run_pipeline.py --years 2015-2024
  micro-slice:   python scripts/run_pipeline.py --years 2019,2021
  offline:       python scripts/run_pipeline.py --fallback     # reads committed CSV
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline import build_dataset  # noqa: E402


def parse_years(spec: str):
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", default="2015-2024", help="e.g. 2015-2024 or 2019,2021")
    ap.add_argument("--picks", type=int, default=None, help="limit to top-N picks per draft")
    ap.add_argument("--out", default=str(ROOT / "data" / "prospects.csv"))
    ap.add_argument("--fallback", action="store_true", help="read committed CSV; no network")
    ap.add_argument("--no-combine", action="store_true", help="skip nba_api combine fetch")
    args = ap.parse_args()
    out = Path(args.out)

    if args.fallback:
        import pandas as pd
        df = pd.read_csv(out)
        print(f"[fallback] {len(df)} prospects from {out} (no network)")
        return

    years = parse_years(args.years)
    print(f"[live] building {years[0]}-{years[-1]} (throttled ~18 req/min, cached) ...")
    df, unmatched = build_dataset.build(years, picks=args.picks, do_combine=not args.no_combine)

    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    um = ROOT / "data" / "unmatched_report.csv"
    unmatched.to_csv(um, index=False)

    print(f"\nwrote {len(df)} prospects -> {out}")
    print(f"unmatched college joins: {len(unmatched)} -> {um}")
    if len(df):
        ncaa = int((df["level"] == "NCAA").sum())
        comb = int(df["wingspan_in"].notna().sum())
        print(f"  NCAA-resolved: {ncaa}/{len(df)}  |  with combine wingspan: {comb}")
        print(f"  outcome tiers: {df['outcome_tier'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
