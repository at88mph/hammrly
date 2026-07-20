"""Tests for Kubernetes label normalization and Job label map."""
from __future__ import annotations

import unittest

from hammrly_orchestrator.k8s.labels import (
    LABEL_JOB_ID,
    LABEL_MANAGED_BY,
    LABEL_USER_ID,
    VALUE_MANAGED_BY_ORCHESTRATOR,
    base_labels_for_job,
    normalize_job_id_label_value,
    normalize_user_id_label_value,
)


class TestLabelNormalization(unittest.TestCase):
    def test_user_id_plain(self) -> None:
        self.assertEqual(normalize_user_id_label_value("alice"), "alice")

    def test_user_id_hashed_when_special_chars(self) -> None:
        raw = "user@host|oidc"
        v = normalize_user_id_label_value(raw)
        self.assertTrue(v.startswith("u-"))
        self.assertLessEqual(len(v), 63)

    def test_job_id_uuid(self) -> None:
        jid = "550e8400-e29b-41d4-a716-446655440000"
        self.assertEqual(normalize_job_id_label_value(jid), jid)

    def test_job_id_unsafe(self) -> None:
        v = normalize_job_id_label_value("bad:value")
        self.assertTrue(v.startswith("j-"))
        self.assertLessEqual(len(v), 63)


class TestBaseLabels(unittest.TestCase):
    def test_identity_and_managed_by_on_job_labels(self) -> None:
        env = {
            "submission_id": "550e8400-e29b-41d4-a716-446655440001",
            "job_id": "550e8400-e29b-41d4-a716-446655440002",
            "tenant_id": "t1",
            "user_id": "user-1",
            "workload": {"kind": "headless", "name": "n1", "image": "img:latest"},
        }
        uid_l = normalize_user_id_label_value("user-1")
        jid_l = normalize_job_id_label_value(env["job_id"])
        labels = base_labels_for_job(
            env,
            kueue_queue_name="batch",
            user_id_label_value=uid_l,
            job_id_label_value=jid_l,
        )
        self.assertEqual(labels[LABEL_MANAGED_BY], VALUE_MANAGED_BY_ORCHESTRATOR)
        self.assertEqual(labels[LABEL_USER_ID], uid_l)
        self.assertEqual(labels[LABEL_JOB_ID], jid_l)


if __name__ == "__main__":
    unittest.main()
