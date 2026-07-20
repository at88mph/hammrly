"""Pod watch readiness helper."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from kubernetes.client import V1ObjectMeta, V1Pod, V1PodCondition, V1PodStatus

from hammrly_orchestrator.k8s.pod_watch import _pod_is_ready, sync_pods_once


class TestPodIsReady(unittest.TestCase):
    def test_ready_when_condition_true(self) -> None:
        pod = V1Pod(
            status=V1PodStatus(
                conditions=[
                    V1PodCondition(type="Ready", status="True"),
                ],
            ),
        )
        self.assertTrue(_pod_is_ready(pod))

    def test_not_ready_without_condition(self) -> None:
        self.assertFalse(_pod_is_ready(V1Pod(status=V1PodStatus())))


class TestSyncPodsOnce(unittest.TestCase):
    def test_calls_mark_session_ready_for_ready_pod(self) -> None:
        pod = V1Pod(
            metadata=V1ObjectMeta(
                labels={"hammrly.io/submission-id": "660e8400-e29b-41d4-a716-446655440001"},
            ),
            status=V1PodStatus(
                conditions=[V1PodCondition(type="Ready", status="True")],
            ),
        )
        core = MagicMock()
        core.list_namespaced_pod.return_value.items = [pod]
        repo = MagicMock()

        sync_pods_once(
            core=core,
            namespace="default",
            label_selector="hammrly.io/managed-by=orchestrator",
            repository=repo,
        )
        repo.mark_session_ready.assert_called_once_with("660e8400-e29b-41d4-a716-446655440001")


if __name__ == "__main__":
    unittest.main()
