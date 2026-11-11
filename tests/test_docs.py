"""Documentation guards: schema fields are documented, README links resolve."""

import dataclasses
import re
from pathlib import Path

import pytest

from ragnostics.schema import GroundTruth, Record, RetrievalEvent, RetrievedSource

REPO = Path(__file__).parent.parent


@pytest.mark.parametrize("cls", [Record, RetrievalEvent, RetrievedSource, GroundTruth])
def test_every_schema_field_is_named_in_schema_md(cls):
    text = (REPO / "docs" / "schema.md").read_text(encoding="utf-8")
    missing = [f.name for f in dataclasses.fields(cls) if f"`{f.name}`" not in text]
    assert not missing, f"{cls.__name__} fields missing from docs/schema.md: {missing}"


def test_readme_links_to_repo_files_exist():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    broken = []
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if re.match(r"^(https?:|mailto:|#)", target):
            continue
        path = target.split("#", 1)[0]
        if path and not (REPO / path).exists():
            broken.append(target)
    assert not broken, f"README links to missing files: {broken}"
