"""Interactive workload pod template: ports, probes, kind env."""
from __future__ import annotations

import unittest

from kubernetes.client import V1Container

from hammrly_orchestrator.k8s.pod_spec import (
    DESKTOP_SHM_VOLUME_NAME,
    build_pod_template,
    workload_container_port,
)


def _notebook_workload(**extra: object) -> dict:
    w = {
        "kind": "notebook",
        "name": "nb",
        "image": "jupyter/minimal-notebook:latest",
        "resources": {"cpu": "200m"},
        "needs_service": True,
        "needs_ingress": True,
        "kind_options": {"jupyter": {"port": 8888}},
    }
    w.update(extra)
    return w


def _desktop_workload(**extra: object) -> dict:
    w = {
        "kind": "desktop",
        "name": "desk",
        "image": "registry.example/hammrly/desktop-astronomy:1.0",
        "resources": {
            "cpu": "4",
            "memory": "8Gi",
        },
        "needs_service": True,
        "needs_ingress": True,
        "kind_options": {"novnc": {"port": 6080}},
    }
    w.update(extra)
    return w


_INGRESS_PATH = "/hammrly/sessions/00000000-0000-4000-8000-000000000003"


class TestInteractivePodSpec(unittest.TestCase):
    def test_notebook_declares_port_and_readiness_probe(self) -> None:
        tpl = build_pod_template(
            _notebook_workload(),
            {"hammrly.io/submission-id": "00000000-0000-4000-8000-000000000001"},
            gpu_node_label_key="k",
            gpu_node_label_value="v",
            ingress_path="/hammrly/sessions/00000000-0000-4000-8000-000000000001",
        )
        spec = tpl.spec
        assert spec is not None
        workload = next(c for c in spec.containers if c.name == "workload")
        self.assertIsInstance(workload, V1Container)
        self.assertEqual(len(workload.ports or []), 1)
        self.assertEqual(workload.ports[0].container_port, 8888)
        self.assertIsNotNone(workload.readiness_probe)
        env_names = {e.name for e in workload.env or []}
        self.assertIn("NOTEBOOK_ARGS", env_names)
        notebook_args = next(e.value for e in workload.env or [] if e.name == "NOTEBOOK_ARGS")
        self.assertIn("ServerApp.base_url=", notebook_args)
        self.assertIn("/hammrly/sessions/", notebook_args)
        # Must not override image entrypoint/CMD (causes exec of the flag as a binary).
        self.assertIsNone(workload.command)
        self.assertIsNone(workload.args)

    def test_headless_has_no_service_probes(self) -> None:
        wl = {
            "kind": "headless",
            "name": "batch",
            "image": "busybox:latest",
            "resources": {"cpu": "100m"},
            "needs_service": False,
            "needs_ingress": False,
            "kind_options": {"batch": {"command": ["true"]}},
        }
        tpl = build_pod_template(
            wl,
            {"hammrly.io/submission-id": "00000000-0000-4000-8000-000000000002"},
            gpu_node_label_key="k",
            gpu_node_label_value="v",
        )
        workload = next(c for c in tpl.spec.containers if c.name == "workload")
        self.assertFalse(workload.ports)
        self.assertIsNone(workload.readiness_probe)

    def test_workload_container_port_notebook(self) -> None:
        self.assertEqual(workload_container_port(_notebook_workload()), 8888)

    def test_notebook_disables_jupyter_token_when_ingress_auth_enabled(self) -> None:
        tpl = build_pod_template(
            _notebook_workload(),
            {"hammrly.io/submission-id": "00000000-0000-4000-8000-000000000001"},
            gpu_node_label_key="k",
            gpu_node_label_value="v",
            ingress_path="/hammrly/sessions/00000000-0000-4000-8000-000000000001",
            ingress_auth_disable_jupyter_token=True,
        )
        workload = next(c for c in tpl.spec.containers if c.name == "workload")
        notebook_args = next(e.value for e in workload.env or [] if e.name == "NOTEBOOK_ARGS")
        self.assertIn("--ServerApp.token=''", notebook_args)

    def test_desktop_declares_port_probes_and_novnc_env(self) -> None:
        tpl = build_pod_template(
            _desktop_workload(),
            {"hammrly.io/submission-id": "00000000-0000-4000-8000-000000000003"},
            gpu_node_label_key="k",
            gpu_node_label_value="v",
            ingress_path=_INGRESS_PATH,
        )
        spec = tpl.spec
        assert spec is not None
        workload = next(c for c in spec.containers if c.name == "workload")
        self.assertEqual(workload.ports[0].container_port, 6080)
        self.assertIsNotNone(workload.readiness_probe)
        self.assertIsNotNone(workload.startup_probe)
        assert workload.readiness_probe.http_get is not None
        self.assertEqual(workload.readiness_probe.http_get.path, f"{_INGRESS_PATH}/")
        path_prefix = next(e.value for e in workload.env or [] if e.name == "NOVNC_PATH_PREFIX")
        self.assertIn("/hammrly/sessions/", path_prefix)
        self.assertIsNone(workload.command)
        self.assertIsNone(workload.args)

    def test_workload_container_port_desktop(self) -> None:
        self.assertEqual(workload_container_port(_desktop_workload()), 6080)

    def test_desktop_mounts_dev_shm_volume(self) -> None:
        tpl = build_pod_template(
            _desktop_workload(),
            {"hammrly.io/submission-id": "00000000-0000-4000-8000-000000000003"},
            gpu_node_label_key="k",
            gpu_node_label_value="v",
            ingress_path=_INGRESS_PATH,
            desktop_shm_size="2Gi",
        )
        spec = tpl.spec
        assert spec is not None
        workload = next(c for c in spec.containers if c.name == "workload")
        shm_mount = next(m for m in workload.volume_mounts or [] if m.mount_path == "/dev/shm")
        self.assertEqual(shm_mount.name, DESKTOP_SHM_VOLUME_NAME)
        shm_vol = next(v for v in spec.volumes or [] if v.name == DESKTOP_SHM_VOLUME_NAME)
        assert shm_vol.empty_dir is not None
        self.assertEqual(shm_vol.empty_dir.medium, "Memory")
        self.assertEqual(shm_vol.empty_dir.size_limit, "2Gi")

    def test_notebook_has_no_dev_shm_volume(self) -> None:
        tpl = build_pod_template(
            _notebook_workload(),
            {"hammrly.io/submission-id": "00000000-0000-4000-8000-000000000001"},
            gpu_node_label_key="k",
            gpu_node_label_value="v",
            ingress_path="/hammrly/sessions/00000000-0000-4000-8000-000000000001",
        )
        spec = tpl.spec
        assert spec is not None
        workload = next(c for c in spec.containers if c.name == "workload")
        self.assertFalse(any(m.mount_path == "/dev/shm" for m in workload.volume_mounts or []))
        self.assertFalse(any(v.name == DESKTOP_SHM_VOLUME_NAME for v in spec.volumes or []))


if __name__ == "__main__":
    unittest.main()
