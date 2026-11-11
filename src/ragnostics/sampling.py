"""Stratified sampling for the open-coding phase."""

from __future__ import annotations

import random
from collections import defaultdict

from .schema import Record


def stratified_sample(records: list[Record], per_source_type: int, seed: int) -> list[str]:
    """Draw ``per_source_type`` record ids per source type, deterministically.

    Records are grouped by ``source_type``; within each group the draw is a
    seeded shuffle, so the same (records, seed) always yields the same sample.
    """
    by_type: dict[str, list[str]] = defaultdict(list)
    for r in records:
        by_type[r.source_type].append(r.id)

    rng = random.Random(seed)
    sample: list[str] = []
    for source_type in sorted(by_type):
        ids = sorted(by_type[source_type])
        rng.shuffle(ids)
        sample.extend(ids[:per_source_type])
    return sample
