"""Pod spec: GPU resources and node affinity."""
from __future__ import annotations

import unittest
from typing import Any

from kubernetes.client import (
    V1Container,
    V1PodSecurityContext,
    V1PodSpec,
    V1ResourceRequirements,
    V1SecurityContext,
    V1Volume,
    V1VolumeMount,
)

from hammrly_orchestrator.k8s.pod_spec import (
    DEFAULT_COMPLETION_FILE,
    DEFAULT_ERROR_FILE,
    DEFAULT_WORKSPACE_MOUNT_PATH,
    NVIDIA_GPU_RESOURCE_NAME,
    WORKSPACE_VOLUME_NAME,
    build_pod_template,
    effective_gpu_count,
)


def _base_workload(**kwargs: Any) -> dict[str, Any]:
    w: dict[str, Any] = {
        "kind": "headless",
        "name": "test-job",
        "image": "busybox:latest",
        "resources": {"cpu": "200m"},
        "needs_ingress": False,
        "needs_service": False,
        "kind_options": {"batch": {"command": ["sleep"], "args": ["1"]}},
    }
    w.update(kwargs)
    return w


LABEL_KEY = "skaha.opencadc.org/node-type"
LABEL_VAL = "gpu-worker-node"


def _env_map(container: V1Container) -> dict[str, str]:
    return {e.name: e.value for e in container.env or []}


def _has_workspace_mount(container: V1Container) -> bool:
    mounts = container.volume_mounts or []
    return any(
        isinstance(m, V1VolumeMount)
        and m.name == WORKSPACE_VOLUME_NAME
        and m.mount_path == DEFAULT_WORKSPACE_MOUNT_PATH
        for m in mounts
    )


class TestEffectiveGpuCount(unittest.TestCase):
    def test_explicit_zero(self) -> None:
        w = _base_workload(gpu_count=0, resources={"nvidia.com/gpu": "1"})
        self.assertEqual(effective_gpu_count(w), 0)

    def test_explicit_wins(self) -> None:
        w = _base_workload(gpu_count=2, resources={NVIDIA_GPU_RESOURCE_NAME: "1"})
        self.assertEqual(effective_gpu_count(w), 2)

    def test_legacy_resources_only(self) -> None:
        w = _base_workload(
            resources={"cpu": "1", NVIDIA_GPU_RESOURCE_NAME: "3"}
        )
        self.assertEqual(effective_gpu_count(w), 3)


class TestBuildPodTemplateGpuScheduling(unittest.TestCase):
    def _tpl(self, workload: dict[str, Any]) -> Any:
        return build_pod_template(
            workload,
            {"hammrly.io/submission-id": "00000000-0000-4000-8000-000000000001"},
            gpu_node_label_key=LABEL_KEY,
            gpu_node_label_value=LABEL_VAL,
        )

    def test_zero_gpu_excludes_gpu_nodes(self) -> None:
        tpl = self._tpl(_base_workload(gpu_count=0))
        spec = tpl.spec
        assert isinstance(spec, V1PodSpec)
        assert spec.affinity and spec.affinity.node_affinity
        na = spec.affinity.node_affinity
        term = na.required_during_scheduling_ignored_during_execution.node_selector_terms[0]
        expr = term.match_expressions[0]
        self.assertEqual(expr.key, LABEL_KEY)
        self.assertEqual(expr.operator, "NotIn")
        self.assertEqual(expr.values, [LABEL_VAL])
        self.assertFalse(spec.tolerations)

    def test_positive_gpu_requires_gpu_nodes_and_devices(self) -> None:
        tpl = self._tpl(_base_workload(gpu_count=2))
        spec = tpl.spec
        assert isinstance(spec, V1PodSpec)
        na = spec.affinity.node_affinity
        term = na.required_during_scheduling_ignored_during_execution.node_selector_terms[0]
        expr = term.match_expressions[0]
        self.assertEqual(expr.operator, "In")
        self.assertEqual(expr.values, [LABEL_VAL])
        self.assertTrue(spec.tolerations)
        c0 = spec.containers[0]
        assert isinstance(c0, V1Container)
        assert isinstance(c0.resources, V1ResourceRequirements)
        self.assertEqual(c0.resources.requests.get(NVIDIA_GPU_RESOURCE_NAME), "2")
        self.assertEqual(c0.resources.limits.get(NVIDIA_GPU_RESOURCE_NAME), "2")

    def test_cpu_request_matches_limit(self) -> None:
        tpl = self._tpl(_base_workload())
        spec = tpl.spec
        assert isinstance(spec, V1PodSpec)
        c0 = spec.containers[0]
        assert isinstance(c0, V1Container)
        assert isinstance(c0.resources, V1ResourceRequirements)
        self.assertEqual(c0.resources.requests.get("cpu"), "200m")
        self.assertEqual(c0.resources.limits.get("cpu"), "200m")

    def test_ephemeral_storage_defaults_to_20g(self) -> None:
        tpl = self._tpl(_base_workload())
        spec = tpl.spec
        assert isinstance(spec, V1PodSpec)
        c0 = spec.containers[0]
        assert isinstance(c0, V1Container)
        assert isinstance(c0.resources, V1ResourceRequirements)
        self.assertEqual(c0.resources.requests.get("ephemeral-storage"), "20G")

    def test_ephemeral_storage_request_can_use_configured_max(self) -> None:
        w = _base_workload(resources={"cpu": "1", "ephemeral_storage": "30"})
        tpl = build_pod_template(
            w,
            {"hammrly.io/submission-id": "00000000-0000-4000-8000-000000000001"},
            gpu_node_label_key=LABEL_KEY,
            gpu_node_label_value=LABEL_VAL,
            max_ephemeral_storage="40",
        )
        spec = tpl.spec
        assert isinstance(spec, V1PodSpec)
        c0 = spec.containers[0]
        assert isinstance(c0, V1Container)
        assert isinstance(c0.resources, V1ResourceRequirements)
        self.assertEqual(c0.resources.requests.get("ephemeral-storage"), "30G")

    def test_ephemeral_storage_request_over_max_rejected(self) -> None:
        w = _base_workload(resources={"cpu": "1", "ephemeral_storage": "30"})
        with self.assertRaises(ValueError):
            self._tpl(w)

    def test_ephemeral_storage_request_rejects_non_gb_units(self) -> None:
        w = _base_workload(resources={"cpu": "1", "ephemeral_storage": "30Gi"})
        with self.assertRaises(ValueError):
            self._tpl(w)

    def test_workload_security_context_is_non_root_and_no_escalation(self) -> None:
        tpl = self._tpl(_base_workload())
        spec = tpl.spec
        assert isinstance(spec, V1PodSpec)
        pod_sc = spec.security_context
        assert isinstance(pod_sc, V1PodSecurityContext)
        self.assertTrue(pod_sc.run_as_non_root)
        self.assertEqual(pod_sc.run_as_user, 1000)
        self.assertEqual(pod_sc.run_as_group, 1000)
        self.assertEqual(pod_sc.fs_group, 1000)
        assert pod_sc.seccomp_profile is not None
        self.assertEqual(pod_sc.seccomp_profile.type, "RuntimeDefault")

        c0 = spec.containers[0]
        assert isinstance(c0, V1Container)
        csc = c0.security_context
        assert isinstance(csc, V1SecurityContext)
        self.assertFalse(csc.allow_privilege_escalation)
        self.assertFalse(csc.privileged)
        self.assertTrue(csc.run_as_non_root)
        self.assertEqual(csc.run_as_user, 1000)
        self.assertEqual(csc.run_as_group, 1000)
        assert csc.capabilities is not None
        self.assertEqual(csc.capabilities.drop, ["ALL"])
        assert csc.seccomp_profile is not None
        self.assertEqual(csc.seccomp_profile.type, "RuntimeDefault")

    def test_workload_security_context_uses_configured_uid_gid(self) -> None:
        tpl = build_pod_template(
            _base_workload(),
            {"hammrly.io/submission-id": "00000000-0000-4000-8000-000000000001"},
            gpu_node_label_key=LABEL_KEY,
            gpu_node_label_value=LABEL_VAL,
            job_run_as_user=2000,
            job_run_as_group=3000,
        )
        spec = tpl.spec
        assert isinstance(spec, V1PodSpec)
        assert isinstance(spec.security_context, V1PodSecurityContext)
        self.assertEqual(spec.security_context.run_as_user, 2000)
        self.assertEqual(spec.security_context.run_as_group, 3000)
        self.assertEqual(spec.security_context.fs_group, 3000)
        c0 = spec.containers[0]
        assert isinstance(c0, V1Container)
        assert isinstance(c0.security_context, V1SecurityContext)
        self.assertEqual(c0.security_context.run_as_user, 2000)
        self.assertEqual(c0.security_context.run_as_group, 3000)

    def test_workspace_emptydir_is_shared_by_init_workload_and_sidecar(self) -> None:
        tpl = self._tpl(_base_workload(input_uri="https://example.test/input.fits"))
        spec = tpl.spec
        assert isinstance(spec, V1PodSpec)

        volumes = spec.volumes or []
        self.assertEqual(len(volumes), 1)
        volume = volumes[0]
        assert isinstance(volume, V1Volume)
        self.assertEqual(volume.name, WORKSPACE_VOLUME_NAME)
        self.assertIsNotNone(volume.empty_dir)

        init = (spec.init_containers or [])[0]
        workload = spec.containers[0]
        sidecar = spec.containers[1]
        assert isinstance(init, V1Container)
        assert isinstance(workload, V1Container)
        assert isinstance(sidecar, V1Container)
        self.assertEqual(init.name, "input-downloader")
        self.assertEqual(workload.name, "workload")
        self.assertEqual(sidecar.name, "output-watcher")
        self.assertTrue(_has_workspace_mount(init))
        self.assertTrue(_has_workspace_mount(workload))
        self.assertTrue(_has_workspace_mount(sidecar))

        workload_env = _env_map(workload)
        self.assertEqual(workload_env["HAMMRLY_WORKSPACE"], DEFAULT_WORKSPACE_MOUNT_PATH)
        self.assertEqual(workload_env["HAMMRLY_INPUT_DIR"], "/workspace/inputs")
        self.assertEqual(workload_env["HAMMRLY_OUTPUT_DIR"], "/workspace/outputs")
        self.assertEqual(workload_env["HAMMRLY_COMPLETION_FILE"], f"/workspace/{DEFAULT_COMPLETION_FILE}")
        self.assertEqual(workload_env["HAMMRLY_ERROR_FILE"], f"/workspace/{DEFAULT_ERROR_FILE}")
        self.assertEqual(_env_map(init)["HAMMRLY_INPUT_URI"], "https://example.test/input.fits")

    def test_workspace_helper_settings_are_configurable(self) -> None:
        tpl = build_pod_template(
            _base_workload(input_uri="file:///tmp/input.dat", output_uri="file:///tmp/out/"),
            {"hammrly.io/submission-id": "00000000-0000-4000-8000-000000000001"},
            gpu_node_label_key=LABEL_KEY,
            gpu_node_label_value=LABEL_VAL,
            workspace_mount_path="/scratch",
            workspace_transfer_image="example.com/hammrly-transfer:test",
            workspace_completion_file="done.json",
            workspace_error_file="failed.json",
        )
        spec = tpl.spec
        assert isinstance(spec, V1PodSpec)
        init = (spec.init_containers or [])[0]
        workload = spec.containers[0]
        sidecar = spec.containers[1]
        assert isinstance(init, V1Container)
        assert isinstance(workload, V1Container)
        assert isinstance(sidecar, V1Container)

        self.assertEqual(init.image, "example.com/hammrly-transfer:test")
        self.assertEqual(sidecar.image, "example.com/hammrly-transfer:test")
        self.assertEqual(_env_map(workload)["HAMMRLY_COMPLETION_FILE"], "/scratch/done.json")
        self.assertEqual(_env_map(workload)["HAMMRLY_ERROR_FILE"], "/scratch/failed.json")
        self.assertEqual(_env_map(sidecar)["HAMMRLY_OUTPUT_URI"], "file:///tmp/out/")


if __name__ == "__main__":
    unittest.main()
