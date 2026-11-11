from __future__ import annotations

import logging
from typing import Any

from kubernetes import client, config
from kubernetes.client import V1ConfigMap, V1ObjectMeta
from kubernetes.client.exceptions import ApiException
from kubernetes.config import ConfigException

from hammrly_orchestrator.campaign.items_manifest import (
    build_items_manifest_document,
    serialize_items_manifest,
)
from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.k8s.jobset_spec import (
    batch_backoff_limit,
    batch_parallelism,
    campaign_template_for_indexed_job,
)
from hammrly_orchestrator.k8s.labels import (
    KUEUE_LOCAL_QUEUE_LABEL,
    base_labels_for_campaign_jobset,
    normalize_user_id_label_value,
    resource_names_from_campaign,
)
from hammrly_orchestrator.k8s.pod_spec import build_pod_template

logger = logging.getLogger(__name__)


class JobSetSubmitter:
    """Creates ConfigMap + suspended JobSet for a campaign."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._configure_client()
        self._core = client.CoreV1Api()
        self._custom = client.CustomObjectsApi()
        self._api = client.ApiClient()

    def _configure_client(self) -> None:
        try:
            config.load_incluster_config()
        except ConfigException:
            path = self._settings.k8s_kubeconfig_path
            if path:
                config.load_kube_config(config_file=path)
            else:
                config.load_kube_config()

    def submit_campaign(
        self,
        campaign_envelope: dict[str, Any],
        *,
        manifest_entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ns = self._settings.k8s_namespace
        campaign_id = str(campaign_envelope["campaign_id"])
        template = campaign_envelope["template"]
        item_count = len(manifest_entries)
        if item_count < 1:
            raise ValueError("campaign JobSet requires at least one item")

        queue_name = self._settings.kueue_local_queue_for_workload_kind("headless")
        user_label = normalize_user_id_label_value(campaign_envelope["user_id"])
        labels = base_labels_for_campaign_jobset(
            campaign_envelope,
            kueue_queue_name=queue_name,
            user_id_label_value=user_label,
        )
        pod_labels = {k: v for k, v in labels.items() if k != KUEUE_LOCAL_QUEUE_LABEL}

        jobset_name, cm_name, _ = resource_names_from_campaign(campaign_id)
        manifest_doc = build_items_manifest_document(campaign_envelope, manifest_entries)
        manifest_bytes = serialize_items_manifest(manifest_doc)
        if len(manifest_bytes) > self._settings.campaign_items_configmap_max_bytes:
            raise ValueError(
                f"campaign items manifest size {len(manifest_bytes)} exceeds "
                f"maximum {self._settings.campaign_items_configmap_max_bytes}"
            )

        cm = V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            metadata=V1ObjectMeta(
                name=cm_name,
                namespace=ns,
                labels=labels,
            ),
            data={"items.json": manifest_bytes.decode("utf-8")},
        )
        self._create_configmap(ns, cm)

        workload = campaign_template_for_indexed_job(template)
        pod_template = build_pod_template(
            workload,
            pod_labels,
            gpu_node_label_key=self._settings.k8s_gpu_node_label_key,
            gpu_node_label_value=self._settings.k8s_gpu_node_label_value,
            default_ephemeral_storage=self._settings.k8s_ephemeral_storage_default,
            max_ephemeral_storage=self._settings.k8s_ephemeral_storage_max,
            job_run_as_user=self._settings.k8s_job_run_as_user,
            job_run_as_group=self._settings.k8s_job_run_as_group,
            workspace_mount_path=self._settings.k8s_workspace_mount_path,
            workspace_transfer_image=self._settings.k8s_workspace_transfer_image,
            workspace_completion_file=self._settings.k8s_workspace_completion_file,
            workspace_error_file=self._settings.k8s_workspace_error_file,
            desktop_shm_size=self._settings.k8s_desktop_shm_default,
            campaign_indexed=True,
            items_configmap_name=cm_name,
        )
        pod_dict = self._api.sanitize_for_serialization(pod_template)

        parallelism = batch_parallelism(template, item_count=item_count)
        backoff = batch_backoff_limit(template)
        child_job: dict[str, Any] = {
            "completionMode": "Indexed",
            "completions": item_count,
            "parallelism": parallelism,
            "template": pod_dict,
        }
        if backoff is not None:
            child_job["backoffLimit"] = backoff

        body: dict[str, Any] = {
            "apiVersion": f"{self._settings.jobset_api_group}/{self._settings.jobset_api_version}",
            "kind": "JobSet",
            "metadata": {
                "name": jobset_name,
                "namespace": ns,
                "labels": labels,
            },
            "spec": {
                "suspend": True,
                "replicatedJobs": [
                    {
                        "name": "workers",
                        "replicas": 1,
                        "template": {"spec": child_job},
                    }
                ],
            },
        }

        created = self._create_jobset(ns, body)
        meta = created.get("metadata") or {}
        return {
            "jobset_name": str(meta.get("name") or jobset_name),
            "jobset_uid": str(meta.get("uid") or ""),
            "resource_version": str(meta.get("resourceVersion") or ""),
            "configmap_name": cm_name,
            "child_job_name": jobset_name,
        }

    def _create_configmap(self, ns: str, cm: V1ConfigMap) -> V1ConfigMap:
        name = cm.metadata.name
        try:
            out = self._core.create_namespaced_config_map(namespace=ns, body=cm)
            logger.info("Created ConfigMap %s/%s", ns, name)
            return out
        except ApiException as e:
            if e.status == 409:
                logger.info("ConfigMap already exists %s/%s", ns, name)
                return self._core.read_namespaced_config_map(name=name, namespace=ns)
            raise

    def _create_jobset(self, ns: str, body: dict[str, Any]) -> dict[str, Any]:
        name = body["metadata"]["name"]
        group = self._settings.jobset_api_group
        version = self._settings.jobset_api_version
        plural = self._settings.jobset_plural
        try:
            out = self._custom.create_namespaced_custom_object(
                group=group,
                version=version,
                namespace=ns,
                plural=plural,
                body=body,
            )
            logger.info("Created JobSet %s/%s", ns, name)
            return out
        except ApiException as e:
            if e.status == 409:
                logger.info("JobSet already exists %s/%s", ns, name)
                return self._custom.get_namespaced_custom_object(
                    group=group,
                    version=version,
                    namespace=ns,
                    plural=plural,
                    name=name,
                )
            logger.error("JobSet create failed status=%s reason=%s body=%s", e.status, e.reason, e.body)
            raise
