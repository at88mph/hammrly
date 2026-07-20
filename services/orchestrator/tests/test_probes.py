"""Probe contract resolution and Kubernetes rendering."""
from __future__ import annotations

import unittest

from kubernetes.client import V1HTTPGetAction, V1Probe

from hammrly_orchestrator.k8s.probes import (
    default_probes_for_kind,
    kind_runtime_env_vars,
    render_container_probes,
    resolve_probe_path,
    resolve_probe_port,
    resolve_workload_probes,
)


class TestProbeResolution(unittest.TestCase):
    def test_resolve_probe_path_ingress_placeholder(self) -> None:
        path = resolve_probe_path("{ingress_path}/api", ingress_path="/hammrly/sessions/abc")
        self.assertEqual(path, "/hammrly/sessions/abc/api")

    def test_resolve_probe_port_workload_literal(self) -> None:
        self.assertEqual(resolve_probe_port("workload", workload_port=8888), 8888)

    def test_default_notebook_probes_when_omitted(self) -> None:
        probes = resolve_workload_probes({"kind": "notebook", "kind_options": {}})
        self.assertIn("readiness", probes)
        self.assertEqual(probes["readiness"]["httpGet"]["port"], "workload")

    def test_explicit_probes_override_defaults(self) -> None:
        wl = {
            "kind": "notebook",
            "kind_options": {
                "probes": {
                    "readiness": {
                        "httpGet": {"path": "/healthz", "port": 9090},
                    },
                },
            },
        }
        probes = resolve_workload_probes(wl)
        self.assertEqual(probes["readiness"]["httpGet"]["path"], "/healthz")

    def test_render_http_readiness_probe(self) -> None:
        probes = default_probes_for_kind("notebook")
        readiness, liveness, startup = render_container_probes(
            probes,
            ingress_path="/hammrly/sessions/sid",
            workload_port=8888,
        )
        self.assertIsInstance(readiness, V1Probe)
        self.assertIsNone(liveness)
        self.assertIsNone(startup)
        assert isinstance(readiness.http_get, V1HTTPGetAction)
        self.assertEqual(readiness.http_get.port, 8888)
        self.assertEqual(readiness.http_get.path, "/hammrly/sessions/sid/api")

    def test_notebook_token_disabled_via_disable_jupyter_token(self) -> None:
        env = kind_runtime_env_vars(
            {"kind": "notebook", "kind_options": {"jupyter": {"port": 8888}}},
            ingress_path="/session/notebook/abc",
            disable_jupyter_token=True,
        )
        args = next(e.value for e in env if e.name == "NOTEBOOK_ARGS")
        self.assertIn("--ServerApp.token=''", args)

    def test_default_desktop_probes_when_omitted(self) -> None:
        probes = resolve_workload_probes({"kind": "desktop", "kind_options": {}})
        self.assertIn("readiness", probes)
        self.assertIn("startup", probes)
        self.assertEqual(probes["readiness"]["httpGet"]["path"], "{ingress_path}/")
        self.assertEqual(probes["startup"]["httpGet"]["path"], "{ingress_path}/")

    def test_render_desktop_probes_with_ingress_path(self) -> None:
        probes = default_probes_for_kind("desktop")
        readiness, liveness, startup = render_container_probes(
            probes,
            ingress_path="/hammrly/sessions/desktop/sid",
            workload_port=6080,
        )
        self.assertIsInstance(readiness, V1Probe)
        self.assertIsInstance(startup, V1Probe)
        self.assertIsNone(liveness)
        assert isinstance(readiness.http_get, V1HTTPGetAction)
        assert isinstance(startup.http_get, V1HTTPGetAction)
        self.assertEqual(readiness.http_get.port, 6080)
        self.assertEqual(readiness.http_get.path, "/hammrly/sessions/desktop/sid/")
        self.assertEqual(startup.failure_threshold, 30)

    def test_desktop_novnc_path_prefix_env(self) -> None:
        env = kind_runtime_env_vars(
            {"kind": "desktop", "kind_options": {"novnc": {"port": 6080}}},
            ingress_path="/hammrly/sessions/desktop/abc",
        )
        prefix = next(e.value for e in env if e.name == "NOVNC_PATH_PREFIX")
        self.assertIn("/hammrly/sessions/desktop/abc", prefix)


if __name__ == "__main__":
    unittest.main()
