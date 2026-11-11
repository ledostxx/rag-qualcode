"""Axial coding LLM call: base_url handling and the JSON-format retry (no network)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import openai
import pytest

from rag_qualcode.ui import axial_coding


def _completion(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _bad_request() -> openai.BadRequestError:
    # A stand-in response keeps the test independent of the HTTP library openai uses.
    response = MagicMock(status_code=400, headers={})
    return openai.BadRequestError("response_format unsupported", response=response, body=None)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    axial_coding._NO_JSON_FORMAT.clear()
    yield
    axial_coding._NO_JSON_FORMAT.clear()


def _patched(responses):
    """Patch ``openai.OpenAI``; returns (patcher, client class mock, create mock)."""
    create = MagicMock(side_effect=responses)
    client = MagicMock()
    client.chat.completions.create = create
    return patch("openai.OpenAI", return_value=client), create


def test_base_url_is_passed_to_the_client():
    patcher, _ = _patched([_completion('{"a": 1}')])
    with patcher as cls:
        result = axial_coding._call("p", "m", 0.0, "key", "http://localhost:11434/v1")
    assert result == {"a": 1}
    cls.assert_called_once_with(api_key="key", base_url="http://localhost:11434/v1")


def test_without_base_url_the_client_gets_only_the_key():
    patcher, _ = _patched([_completion("{}")])
    with patcher as cls:
        axial_coding._call("p", "m", 0.0, "key")
    cls.assert_called_once_with(api_key="key")


def test_first_attempt_sends_json_response_format():
    patcher, create = _patched([_completion('{"a": 1}')])
    with patcher:
        axial_coding._call("p", "m", 0.2, "key", "http://e/v1")
    assert create.call_count == 1
    assert create.call_args.kwargs["response_format"] == {"type": "json_object"}


def test_bad_request_retries_once_without_response_format():
    patcher, create = _patched([_bad_request(), _completion('{"ok": true}')])
    with patcher:
        result = axial_coding._call("p", "m", 0.0, "key", "http://e/v1")
    assert result == {"ok": True}
    assert create.call_count == 2
    assert "response_format" not in create.call_args_list[1].kwargs
    assert axial_coding._NO_JSON_FORMAT["http://e/v1"] is True


def test_non_json_reply_retries_once_and_extracts_the_object():
    patcher, create = _patched([_completion("Sure! here it is"), _completion('Reply: {"k": 2} done')])
    with patcher:
        result = axial_coding._call("p", "m", 0.0, "key", "http://e/v1")
    assert result == {"k": 2}
    assert create.call_count == 2
    assert "response_format" not in create.call_args_list[1].kwargs
    # A non-JSON reply does not mark the endpoint as format-incapable.
    assert not axial_coding._NO_JSON_FORMAT.get("http://e/v1")


def test_later_call_with_same_base_url_skips_the_first_attempt():
    patcher, create = _patched(
        [_bad_request(), _completion("{}"), _completion('{"second": 1}')]
    )
    with patcher:
        axial_coding._call("p", "m", 0.0, "key", "http://e/v1")
        result = axial_coding._call("p", "m", 0.0, "key", "http://e/v1")
    assert result == {"second": 1}
    assert create.call_count == 3  # 2 for the first call, 1 for the second
    assert "response_format" not in create.call_args_list[2].kwargs


def test_other_endpoint_still_tries_the_json_format_first():
    patcher, create = _patched([_bad_request(), _completion("{}"), _completion("{}")])
    with patcher:
        axial_coding._call("p", "m", 0.0, "key", "http://one/v1")
        axial_coding._call("p", "m", 0.0, "key", "http://two/v1")
    assert create.call_args_list[2].kwargs.get("response_format") == {"type": "json_object"}


def test_unparseable_retry_reply_raises():
    patcher, _ = _patched([_completion("no json"), _completion("still none")])
    with patcher, pytest.raises(ValueError):
        axial_coding._call("p", "m", 0.0, "key", "http://e/v1")
