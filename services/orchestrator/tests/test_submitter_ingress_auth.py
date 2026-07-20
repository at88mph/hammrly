"""Session Ingress metadata annotations when edge auth is enabled."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from kubernetes.client import V1Ingress, V1ObjectMeta

from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.k8s.submitter import KubernetesSubmitter


class TestSubmitterIngressAuth(unittest.TestCase):
    def test_create_ingress_applies_auth_annotations(self) -> None:
        settings = Settings.model_validate(
            {
                "database_url": "postgresql+psycopg2://u:p@localhost/db",
                "k8s_ingress_auth_enabled": True,
                "k8s_ingress_auth_annotations": {
                    "traefik.ingress.kubernetes.io/router.middlewares": "hammrly-mw@kubernetescrd",
                },
            }
        )
        submitter = KubernetesSubmitter(settings)
        submitter._net = MagicMock()

        captured: dict[str, object] = {}

        def _capture_create(*, namespace: str, body: V1Ingress) -> V1Ingress:
            captured["namespace"] = namespace
            captured["body"] = body
            return body

        submitter._net.create_namespaced_ingress.side_effect = _capture_create

        submitter._create_ingress(
            "workloads",
            "ing-test",
            "svc-test",
            "sessions.example.com",
            "/session/notebook/abc/",
        )

        body = captured["body"]
        assert isinstance(body, V1Ingress)
        meta = body.metadata
        assert isinstance(meta, V1ObjectMeta)
        self.assertEqual(
            meta.annotations,
            {"traefik.ingress.kubernetes.io/router.middlewares": "hammrly-mw@kubernetescrd"},
        )

    @patch.object(KubernetesSubmitter, "_configure_client")
    def test_create_ingress_omits_annotations_when_auth_disabled(self, _mock_cfg: MagicMock) -> None:
        settings = Settings.model_validate(
            {
                "database_url": "postgresql+psycopg2://u:p@localhost/db",
                "k8s_ingress_auth_enabled": False,
                "k8s_ingress_auth_annotations": {
                    "traefik.ingress.kubernetes.io/router.middlewares": "ignored",
                },
            }
        )
        submitter = KubernetesSubmitter(settings)
        submitter._net = MagicMock()
        captured: dict[str, object] = {}

        def _capture_create(*, namespace: str, body: V1Ingress) -> V1Ingress:
            captured["body"] = body
            return body

        submitter._net.create_namespaced_ingress.side_effect = _capture_create
        submitter._create_ingress("ns", "ing", "svc", "host", "/path/")

        body = captured["body"]
        assert isinstance(body, V1Ingress)
        self.assertIsNone(body.metadata.annotations)


if __name__ == "__main__":
    unittest.main()
