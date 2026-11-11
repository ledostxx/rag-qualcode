"""G6 guard: no absolute home paths or key patterns in tracked files.

The personal email address and benchmark content are checked by the local
script in the thesis folder, not here: neither may be public.
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).parent.parent
PATTERNS = {
    "absolute home path": re.compile(r"/Users/|/home/"),
    "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
}
ALLOW = "privacy-allow"


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [REPO / line for line in out.splitlines() if line]


def test_scan_finds_the_patterns_it_looks_for():
    # Guards the guard against a pattern that silently matches nothing.
    assert PATTERNS["absolute home path"].search("x /Users/someone/file")
    assert PATTERNS["OpenAI-style key"].search("sk-" + "a" * 24)
    assert PATTERNS["Google API key"].search("AIza" + "b" * 35)


def test_tracked_files_hold_no_home_paths_or_keys():
    hits = []
    for path in _tracked_files():
        if path.name == Path(__file__).name or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary file
        for number, line in enumerate(text.splitlines(), start=1):
            if line.rstrip().endswith(ALLOW):
                continue
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    hits.append(f"{path.relative_to(REPO)}:{number}: {label}")
    assert not hits, "\n".join(hits)
