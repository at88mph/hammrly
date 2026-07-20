from __future__ import annotations

import pytest

from hammrly_query.config import Settings


def test_interactive_kinds_must_match_contract_enum() -> None:
    with pytest.raises(ValueError, match="HAMMRLY_INTERACTIVE_KINDS"):
        Settings(interactive_kinds="desktop,not-a-contract-kind")


def test_interactive_kinds_accepts_full_contract_enum() -> None:
    s = Settings(interactive_kinds="desktop,notebook,carta,contributed,headless")
    assert set(s.interactive_kinds_list) == {
        "desktop",
        "notebook",
        "carta",
        "contributed",
        "headless",
    }


def test_http_path_prefix_normalized() -> None:
    assert Settings(http_path_prefix="").http_path_prefix == ""
    assert Settings(http_path_prefix="hammrly/query").http_path_prefix == "/hammrly/query"
    assert Settings(http_path_prefix="/hammrly/query/").http_path_prefix == "/hammrly/query"


def test_http_path_prefix_root_becomes_empty() -> None:
    assert Settings(http_path_prefix="/").http_path_prefix == ""
