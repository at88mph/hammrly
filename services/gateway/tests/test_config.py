from __future__ import annotations

from hammrly_gateway.config import Settings


def test_http_path_prefix_normalized() -> None:
    assert Settings(http_path_prefix="").http_path_prefix == ""
    assert Settings(http_path_prefix="api/v1").http_path_prefix == "/api/v1"
    assert Settings(http_path_prefix="/hammrly/gateway/").http_path_prefix == "/hammrly/gateway"


def test_http_path_prefix_root_becomes_empty() -> None:
    assert Settings(http_path_prefix="/").http_path_prefix == ""
