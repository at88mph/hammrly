"""Ingress edge-auth settings parsing."""
from __future__ import annotations

import unittest

from hammrly_orchestrator.config import Settings


class TestIngressAuthConfig(unittest.TestCase):
    def test_auth_annotations_from_json_string(self) -> None:
        s = Settings.model_validate(
            {
                "database_url": "postgresql+psycopg2://u:p@localhost/db",
                "k8s_ingress_auth_annotations": (
                    '{"traefik.ingress.kubernetes.io/router.middlewares":"ns-mw@kubernetescrd"}'
                ),
            }
        )
        self.assertEqual(
            s.k8s_ingress_auth_annotations,
            {"traefik.ingress.kubernetes.io/router.middlewares": "ns-mw@kubernetescrd"},
        )

    def test_auth_annotations_default_empty(self) -> None:
        s = Settings.model_validate({"database_url": "postgresql+psycopg2://u:p@localhost/db"})
        self.assertEqual(s.k8s_ingress_auth_annotations, {})
        self.assertFalse(s.k8s_ingress_auth_enabled)


if __name__ == "__main__":
    unittest.main()
