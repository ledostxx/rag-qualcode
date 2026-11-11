"""Console entry point.

    qualcode [project.yaml] [--port N]                          start the GUI
    qualcode validate [project.yaml] [--show N] [--traceback]   check an adapter

Wraps ``streamlit run`` so users don't need to know where the app module
lives inside the installed package.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_DEFAULT_PROJECT = "qualcode.yaml"


def _validate(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="qualcode validate",
        description="Load a project's adapter and check the records it produces.",
    )
    parser.add_argument("project", nargs="?", default=_DEFAULT_PROJECT)
    parser.add_argument("--show", type=int, default=3, help="Records to print in full (default 3)")
    parser.add_argument(
        "--traceback", action="store_true", help="Print tracebacks for adapter errors"
    )
    args = parser.parse_args(argv)

    from .config import load_project
    from .validate import format_report, run_validation

    try:
        cfg = load_project(args.project)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Problem: {exc}")
        return 1
    report = run_validation(cfg, args.show, with_traceback=args.traceback)
    print(format_report(report))
    return 1 if report.problems else 0


def main() -> None:
    # The first argument is compared with the literal "validate", so a project
    # file path is never mistaken for a subcommand.
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        sys.exit(_validate(sys.argv[2:]))

    parser = argparse.ArgumentParser(
        prog="qualcode",
        description="Qualitative failure-mode analysis for RAG systems.",
    )
    parser.add_argument(
        "project",
        nargs="?",
        default=_DEFAULT_PROJECT,
        help="Path to the project YAML (default: ./qualcode.yaml)",
    )
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port")
    args = parser.parse_args()

    project = Path(args.project).expanduser().resolve()
    if not project.exists():
        sys.exit(f"Project config not found: {project}")

    from streamlit.web import cli as stcli

    app = Path(__file__).parent / "app.py"
    os.environ["QUALCODE_PROJECT"] = str(project)
    sys.argv = [
        "streamlit",
        "run",
        str(app),
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--client.toolbarMode",
        "minimal",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
