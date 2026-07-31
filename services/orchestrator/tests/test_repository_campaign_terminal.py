"""Campaign terminal rollup and expansion failure persistence."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from hammrly_orchestrator.persistence.models import Campaign, Submission, UserNotification
from hammrly_orchestrator.persistence.repository import SubmissionRepository


class _Ctx:
    def __init__(self, session: MagicMock) -> None:
        self._session = session

    def __enter__(self) -> MagicMock:
        return self._session

    def __exit__(self, *args: object) -> None:
        return None


class TestCampaignTerminal(unittest.TestCase):
    def test_finalize_expansion_sets_active_not_completed(self) -> None:
        camp = Campaign(
            campaign_id="c1",
            tenant_id="t1",
            user_id="u1",
            name="camp",
            status="expanding",
            item_count=2,
            counts_json={"submitted_to_cluster": 2},
            cluster_id="default",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session = MagicMock()
        session.get.return_value = camp
        repo = SubmissionRepository(MagicMock())
        repo._session = lambda: _Ctx(session)  # type: ignore[method-assign]
        repo.finalize_campaign_expansion("c1")
        self.assertEqual(camp.status, "active")

    def test_record_campaign_item_failed_creates_submission(self) -> None:
        camp = Campaign(
            campaign_id="c1",
            tenant_id="t1",
            user_id="u1",
            name="camp",
            status="expanding",
            item_count=1,
            counts_json={},
            template_summary={"kind": "headless", "name": "n", "image": "img", "gpu_count": 0},
            cluster_id="default",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session = MagicMock()
        session.get.return_value = camp
        session.scalar.return_value = None
        # For _maybe_finalize: terminal count == item_count after failed adjust
        session.scalars.return_value.all.return_value = []

        repo = SubmissionRepository(MagicMock())
        repo._session = lambda: _Ctx(session)  # type: ignore[method-assign]
        repo.record_campaign_item_failed("c1", item_key="item-1", detail="bad networking")

        added = [c.args[0] for c in session.add.call_args_list if c.args]
        subs = [a for a in added if isinstance(a, Submission)]
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].status, "failed")
        self.assertEqual(subs[0].item_key, "item-1")
        self.assertIn("bad networking", subs[0].status_detail or "")
        self.assertEqual(camp.status, "failed")
        notes = [a for a in added if isinstance(a, UserNotification)]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].kind, "campaign_terminal")
