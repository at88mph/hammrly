"""Types aligned with Hammrly job-submission contract v1.

Repo: `contracts/job-submission/v1/schema.json` (`JobSubmissionEnvelope` / `WorkloadSpec`).

The database stores an orchestrator-written summary derived from `envelope["workload"]`
(see `hammrly_orchestrator.persistence.repository.SubmissionRepository.record_received`):
`kind`, `name`, `image`, and `gpu_count` — a subset of JSON Schema `WorkloadSpec`.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class WorkloadKind(str, Enum):
    """`$defs.WorkloadKind` in the job-submission v1 JSON Schema."""

    desktop = "desktop"
    notebook = "notebook"
    carta = "carta"
    contributed = "contributed"
    headless = "headless"


class PayloadSummary(BaseModel):
    """Denormalized workload fields persisted in `submissions.payload_summary` (JSONB)."""

    model_config = ConfigDict(extra="ignore")

    kind: Optional[WorkloadKind] = None
    name: Optional[str] = None
    image: Optional[str] = None
    gpu_count: Optional[int] = Field(default=None, ge=0)


def parse_payload_summary(raw: Any) -> Optional[PayloadSummary]:
    """Parse DB JSON into the contract-aligned summary; invalid documents log a warning."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        logger.warning("payload_summary is not a JSON object: %r", raw)
        return None
    try:
        return PayloadSummary.model_validate(raw)
    except ValidationError:
        logger.warning("payload_summary does not match contract workload subset: %r", raw)
        return None
