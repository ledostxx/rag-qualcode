"""Annotation persistence.

One JSON file per project holding open-coding annotations, the drawn sample,
and the axial-coding codebook, prompts and assignments. Writes are atomic
(temp file + rename) so a crash mid-save never corrupts existing annotations.

``codes``, ``code_vocabulary`` and the methods ``known_codes`` and ``add_code`` are
kept for files written before D-004 (open coding is pure free text). New
annotations leave ``codes`` empty.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def _empty_state() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "annotations": {},
        "sample": [],
        "code_vocabulary": [],
        "codebook": [],
    }


class AnnotationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict[str, Any] = _empty_state()
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            self.data.update(loaded)

    # -- open coding annotations ------------------------------------------

    def get(self, record_id: str) -> dict[str, Any]:
        return self.data["annotations"].get(
            record_id, {"codes": [], "note": "", "no_issues": False}
        )

    def set(self, record_id: str, codes: list[str], note: str, no_issues: bool) -> None:
        """Store one record's annotation. ``codes`` is kept for files written before
        D-004 and is empty for new annotations."""
        self.data["annotations"][record_id] = {
            "codes": sorted(set(codes)),
            "note": note,
            "no_issues": no_issues,
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        for code in codes:
            self.add_code(code, save=False)
        self.save()

    def is_coded(self, record_id: str) -> bool:
        ann = self.data["annotations"].get(record_id)
        return bool(ann and (ann["codes"] or ann["note"].strip() or ann["no_issues"]))

    def coded_count(self, ids: list[str] | None = None) -> int:
        pool = ids if ids is not None else list(self.data["annotations"])
        return sum(1 for rid in pool if self.is_coded(rid))

    # -- code vocabulary ---------------------------------------------------

    def known_codes(self) -> list[str]:
        """Kept for files written before D-004; the GUI no longer uses it."""
        codes = set(self.data["code_vocabulary"])
        for ann in self.data["annotations"].values():
            codes.update(ann.get("codes", []))
        return sorted(codes)

    def add_code(self, code: str, save: bool = True) -> None:
        """Kept for files written before D-004; the GUI no longer uses it."""
        code = code.strip()
        if code and code not in self.data["code_vocabulary"]:
            self.data["code_vocabulary"].append(code)
            if save:
                self.save()

    # -- axial phase -------------------------------------------------------

    def axial_prompt(self, default: str = "") -> str:
        """The editable prompt template used to propose axial codes. Persisted so
        prompt iteration survives a restart, which is the point of developing it
        inside the tool rather than in a playground."""
        return self.data.get("axial_prompt") or default

    def set_axial_prompt(self, prompt: str) -> None:
        self.data["axial_prompt"] = prompt
        self.save()

    def codebook(self) -> list[dict[str, Any]]:
        return list(self.data.get("codebook") or [])

    def set_codebook(self, entries: list[dict[str, Any]]) -> None:
        self.data["codebook"] = list(entries)
        self.save()

    def assign_prompt(self, default: str = "") -> str:
        """Prompt for the second axial step, which assigns one open code against the
        reviewed category definitions."""
        return self.data.get("assign_prompt") or default

    def set_assign_prompt(self, prompt: str) -> None:
        self.data["assign_prompt"] = prompt
        self.save()

    def assign_batch_prompt(self, default: str = "") -> str:
        """Prompt for the same second step run in one call on another model. The
        copy button hands this over, so it is persisted alongside the others rather
        than living only as a constant, which would leave no record of what was
        actually sent."""
        return self.data.get("assign_batch_prompt") or default

    def set_assign_batch_prompt(self, prompt: str) -> None:
        self.data["assign_batch_prompt"] = prompt
        self.save()

    def assignments(self) -> list[dict[str, Any]]:
        return list(self.data.get("axial_assignments") or [])

    def set_assignments(self, entries: list[dict[str, Any]]) -> None:
        self.data["axial_assignments"] = list(entries)
        self.save()

    def assignments_for(self) -> list[str]:
        """Category names the stored assignments were made against, so an edit to the
        categories afterwards can be flagged instead of silently mismatching."""
        return list(self.data.get("assignments_for") or [])

    def set_assignments_for(self, names: list[str]) -> None:
        self.data["assignments_for"] = list(names)
        self.save()

    def codebook_frozen_at(self) -> str | None:
        """When the codebook was declared final, or None. Makes it explicit that
        iteration has stopped."""
        return self.data.get("codebook_frozen_at")

    def freeze_codebook(self, frozen: bool = True) -> None:
        self.data["codebook_frozen_at"] = (
            datetime.now(timezone.utc).isoformat(timespec="seconds") if frozen else None
        )
        self.save()

    # -- sample ------------------------------------------------------------

    def sample_ids(self) -> list[str]:
        return list(self.data["sample"])

    def set_sample(self, ids: list[str]) -> None:
        self.data["sample"] = list(ids)
        self.save()

    # -- persistence -------------------------------------------------------

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
