from __future__ import annotations

import pytest

from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.k8s.edge_binding import (
    NoOpEdgeStrategy,
    StandardKubernetesIngressStrategy,
    _join_public_url,
    edge_strategy_for_settings,
    ingress_path_for_workload,
)
from hammrly_orchestrator.networking import normalize_workload_networking


def test_normalize_interactive_defaults() -> None:
    w = normalize_workload_networking(
        {"kind": "desktop", "name": "n", "image": "i", "resources": {"cpu": "1"}}
    )
    assert w["needs_service"] is True and w["needs_ingress"] is True


def test_normalize_headless_defaults() -> None:
    w = normalize_workload_networking(
        {
            "kind": "headless",
            "name": "n",
            "image": "i",
            "resources": {"cpu": "1"},
            "kind_options": {"batch": {"command": ["true"]}},
        }
    )
    assert w["needs_service"] is False and w["needs_ingress"] is False


def test_normalize_interactive_rejects_explicit_false() -> None:
    with pytest.raises(ValueError):
        normalize_workload_networking(
            {
                "kind": "notebook",
                "name": "n",
                "image": "i",
                "resources": {"cpu": "1"},
                "needs_service": False,
                "needs_ingress": True,
            }
        )


def test_ingress_path_per_kind_template() -> None:
    s = Settings.model_construct(
        database_url="postgresql+psycopg2://u:p@localhost/db",
        k8s_ingress_path_prefix="/ham",
        k8s_ingress_path_template_desktop="/session/desktop/{submission_id}/",
    )
    p = ingress_path_for_workload(s, {"kind": "desktop"}, "sub-1")
    assert p == "/session/desktop/sub-1/"


def test_edge_strategy_factory() -> None:
    s = Settings.model_construct(
        database_url="postgresql+psycopg2://u:p@localhost/db",
        k8s_edge_binding="none",
    )
    assert isinstance(edge_strategy_for_settings(s), NoOpEdgeStrategy)
    s2 = Settings.model_construct(
        database_url="postgresql+psycopg2://u:p@localhost/db",
        k8s_edge_binding="standard_ingress",
    )
    assert isinstance(edge_strategy_for_settings(s2), StandardKubernetesIngressStrategy)


def test_join_public_url() -> None:
    assert _join_public_url("https", "h.example", "/p/x/") == "https://h.example/p/x/"
