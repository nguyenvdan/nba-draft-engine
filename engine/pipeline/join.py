"""Name normalization + fuzzy matching for cross-source joins.

Combine names (nba_api) and draft names (BBRef) differ in punctuation, accents,
and generational suffixes. We normalize then match with rapidfuzz, scoped to the
same draft year, with a conservative threshold.
"""
import re

from rapidfuzz import fuzz, process
from unidecode import unidecode

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def norm_name(s: str) -> str:
    s = unidecode(str(s)).lower()
    s = _SUFFIX.sub("", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def match_combine(player: str, combine_df, threshold: int = 88):
    """Best fuzzy match of `player` to a combine-year frame; None if too weak."""
    if combine_df is None or combine_df.empty:
        return None
    keys = [norm_name(n) for n in combine_df["player"]]
    hit = process.extractOne(norm_name(player), keys, scorer=fuzz.token_sort_ratio)
    if hit and hit[1] >= threshold:
        idx = hit[2]  # (choice, score, index)
        row = combine_df.iloc[idx]
        return {c: row[c] for c in combine_df.columns if c != "player"}
    return None
