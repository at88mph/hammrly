from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from kubernetes.client import (
    V1Container,
    V1Job,
    V1JobSpec,
    V1JobStatus,
    V1ObjectMeta,
    V1PodSpec,
    V1PodTemplateSpec,
)

_MIN_TEMPLATE = V1PodTemplateSpec(
    metadata=V1ObjectMeta(),
    spec=V1PodSpec(
        restart_policy="Never",
        containers=[V1Container(name="c", image="busybox")],
    ),
)


class TestMapJobStatus(unittest.TestCase):
    def test_suspended_no_active(self) -> None:
        from hammrly_orchestrator.k8s.job_state import map_job_to_submission_status

        job = V1Job(
            metadata=V1ObjectMeta(name="j1"),
            spec=V1JobSpec(suspend=True, template=_MIN_TEMPLATE),
            status=V1JobStatus(active=0),
        )
        st, _ = map_job_to_submission_status(job)
        self.assertEqual(st, "submitted_to_cluster")

    def test_complete_condition(self) -> None:
        from hammrly_orchestrator.k8s.job_state import map_job_to_submission_status

        cond = MagicMock()
        cond.type = "Complete"
        cond.status = "True"

        job = V1Job(
            metadata=V1ObjectMeta(name="j1"),
            spec=V1JobSpec(suspend=False, template=_MIN_TEMPLATE),
            status=V1JobStatus(conditions=[cond]),
        )
        st, _ = map_job_to_submission_status(job)
        self.assertEqual(st, "succeeded")

    def test_active_running(self) -> None:
        from hammrly_orchestrator.k8s.job_state import map_job_to_submission_status

        job = V1Job(
            metadata=V1ObjectMeta(name="j1"),
            spec=V1JobSpec(suspend=False, template=_MIN_TEMPLATE),
            status=V1JobStatus(active=1),
        )
        st, _ = map_job_to_submission_status(job)
        self.assertEqual(st, "running")


if __name__ == "__main__":
    unittest.main()
