"""Adapter loading by file path and by built-in name."""

import sys
from pathlib import Path

import pytest

from ragnostics.adapters import AdapterLoadError, get_adapter, resolve_adapter_class
from ragnostics.adapters.base import Adapter
from ragnostics.adapters.grains import GrainsAdapter

REPO = Path(__file__).parent.parent
DEMO_DIR = REPO / "examples" / "demo"

_MINIMAL = '''
from ragnostics.adapters.base import Adapter
from ragnostics.schema import Record


class {name}(Adapter):
    name = "{tag}"

    def load(self):
        return [Record(id="{tag}", source_type="t", question="q", system_answer="a")]
'''


def _user_modules() -> set[str]:
    return {m for m in sys.modules if m.startswith("ragnostics_user_adapter_")}


def test_demo_adapter_loads_relative_to_project_folder():
    cls = resolve_adapter_class("./demo_adapter.py:DemoAdapter", DEMO_DIR)
    assert issubclass(cls, Adapter) and cls.__name__ == "DemoAdapter"
    records = get_adapter(
        "./demo_adapter.py:DemoAdapter", {"logs": str(DEMO_DIR / "logs.jsonl")}, DEMO_DIR
    ).load()
    assert len(records) == 20


def test_demo_adapter_loads_by_absolute_path():
    cls = resolve_adapter_class(f"{DEMO_DIR / 'demo_adapter.py'}:DemoAdapter", None)
    assert cls.__name__ == "DemoAdapter"


def test_adapter_file_defining_a_dataclass_loads(tmp_path):
    (tmp_path / "dc_adapter.py").write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        + _MINIMAL.format(name="DcAdapter", tag="dc")
        + "\n\n@dataclass\nclass Helper:\n    x: int = 1\n",
        encoding="utf-8",
    )
    cls = resolve_adapter_class("dc_adapter.py:DcAdapter", tmp_path)
    assert cls({}).load()[0].id == "dc"


def test_same_file_name_in_two_folders_gives_different_classes(tmp_path):
    classes = []
    for tag in ("one", "two"):
        folder = tmp_path / tag
        folder.mkdir()
        (folder / "adapter.py").write_text(
            _MINIMAL.format(name="MyAdapter", tag=tag), encoding="utf-8"
        )
        classes.append(resolve_adapter_class("adapter.py:MyAdapter", folder))
    assert classes[0] is not classes[1]
    assert classes[0]({}).load()[0].id == "one"
    assert classes[1]({}).load()[0].id == "two"


def test_missing_file_names_the_file(tmp_path):
    with pytest.raises(AdapterLoadError) as exc:
        resolve_adapter_class("nowhere.py:Foo", tmp_path)
    assert "nowhere.py" in str(exc.value)


def test_missing_class_names_file_and_class(tmp_path):
    (tmp_path / "a.py").write_text(_MINIMAL.format(name="Real", tag="r"), encoding="utf-8")
    with pytest.raises(AdapterLoadError) as exc:
        resolve_adapter_class("a.py:Ghost", tmp_path)
    assert "a.py" in str(exc.value) and "Ghost" in str(exc.value)


def test_class_that_is_not_an_adapter_names_file_and_class(tmp_path):
    (tmp_path / "b.py").write_text("class NotAnAdapter:\n    pass\n", encoding="utf-8")
    with pytest.raises(AdapterLoadError) as exc:
        resolve_adapter_class("b.py:NotAnAdapter", tmp_path)
    assert "b.py" in str(exc.value) and "NotAnAdapter" in str(exc.value)


def test_syntax_error_raises_and_leaves_no_module(tmp_path):
    (tmp_path / "bad_syntax.py").write_text("def broken(:\n", encoding="utf-8")
    before = _user_modules()
    with pytest.raises(AdapterLoadError) as exc:
        resolve_adapter_class("bad_syntax.py:Whatever", tmp_path)
    assert "bad_syntax.py" in str(exc.value)
    assert _user_modules() == before


def test_builtin_name_resolves_with_and_without_base_dir(tmp_path):
    assert resolve_adapter_class("grains") is GrainsAdapter
    assert resolve_adapter_class("grains", tmp_path) is GrainsAdapter


def test_unknown_builtin_name_is_an_adapter_load_error():
    with pytest.raises(AdapterLoadError) as exc:
        resolve_adapter_class("no-such-adapter")
    assert "no-such-adapter" in str(exc.value)
