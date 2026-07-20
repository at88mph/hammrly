"""SubmissionRepository session readiness transitions."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from hammrly_orchestrator.persistence.models import Submission, SubmissionEvent
from hammrly_orchestrator.persistence.repository import SubmissionRepository


class TestMarkSessionReady(unittest.TestCase):
    def _repo_with_row(self, row: Submission) -> SubmissionRepository:
        repo = SubmissionRepository(MagicMock())
        session = MagicMock()
        session.get.return_value = row
        repo._session = lambda: _Ctx(session)  # type: ignore[method-assign]
        return repo, session

    def test_marks_ready_and_emits_event(self) -> None:
        row = Submission(
            submission_id="660e8400-e29b-41d4-a716-446655440001",
            job_id="550e8400-e29b-41d4-a716-446655440000",
            tenant_id="t1",
            user_id="u1",
            status="running",
            queue_name="default",
            cluster_id="default",
            access_url="https://sessions.example/s/",
            payload_summary={"needs_ingress": True},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        repo, session = self._repo_with_row(row)
        repo.mark_session_ready(row.submission_id)
        self.assertEqual(row.status, "ready")
        added = [c.args[0] for c in session.add.call_args_list if c.args]
        self.assertTrue(any(isinstance(a, SubmissionEvent) and a.event_type == "session_ready" for a in added))

    def test_idempotent_when_already_ready(self) -> None:
        row = Submission(
            submission_id="660e8400-e29b-41d4-a716-446655440002",
            job_id="550e8400-e29b-41d4-a716-446655440000",
            tenant_id="t1",
            user_id="u1",
            status="ready",
            queue_name="default",
            cluster_id="default",
            payload_summary={"needs_ingress": True},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        repo, session = self._repo_with_row(row)
        repo.mark_session_ready(row.submission_id)
        session.add.assert_not_called()

    def test_skips_when_needs_ingress_false(self) -> None:
        row = Submission(
            submission_id="660e8400-e29b-41d4-a716-446655440003",
            job_id="550e8400-e29b-41d4-a716-446655440000",
            tenant_id="t1",
            user_id="u1",
            status="running",
            queue_name="default",
            cluster_id="default",
            payload_summary={"needs_ingress": False},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        repo, session = self._repo_with_row(row)
        repo.mark_session_ready(row.submission_id)
        self.assertEqual(row.status, "running")
        session.add.assert_not_called()


class _Ctx:
    def __init__(self, session: MagicMock) -> None:
        self._session = session

    def __enter__(self) -> MagicMock:
        return self._session

    def __exit__(self, *args: object) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
