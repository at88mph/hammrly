from __future__ import annotations

import logging
from typing import Any, Tuple

from kubernetes import client, config
from kubernetes.client import (
    V1HTTPIngressPath,
    V1HTTPIngressRuleValue,
    V1Ingress,
    V1IngressBackend,
    V1IngressRule,
    V1IngressServiceBackend,
    V1IngressSpec,
    V1Job,
    V1JobSpec,
    V1ObjectMeta,
    V1OwnerReference,
    V1Service,
    V1ServiceBackendPort,
    V1ServicePort,
    V1ServiceSpec,
)
from kubernetes.client.exceptions import ApiException
from kubernetes.config import ConfigException

from hammrly_orchestrator.k8s.pod_spec import (
    workload_container_port,
    build_pod_template,
)
from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.k8s.labels import (
    LABEL_SUBMISSION_ID,
    base_labels_for_job,
    normalize_job_id_label_value,
    normalize_user_id_label_value,
    resource_names_from_submission,
)
from hammrly_orchestrator.k8s.edge_binding import (
    SessionAccessDescriptor,
    edge_strategy_for_settings,
    ingress_path_for_workload,
)

logger = logging.getLogger(__name__)


def job_owner_references(meta: V1ObjectMeta | None) -> list[V1OwnerReference]:
    """Owner ref to the Job so Service/Ingress are garbage-collected when the Job is deleted."""
    if not meta or not meta.name or not meta.uid:
        return []
    return [
        V1OwnerReference(
            api_version="batch/v1",
            kind="Job",
            name=meta.name,
            uid=meta.uid,
            controller=True,
            block_owner_deletion=True,
        )
    ]


class KubernetesSubmitter:
    """
    Creates suspended Jobs for Kueue (kueue.x-k8s.io/queue-name) plus optional Service/Ingress.

    Uses the official ``kubernetes`` Python client (kubernetes-client/python).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._edge_strategy = edge_strategy_for_settings(settings)
        self._configure_client()
        self._batch = client.BatchV1Api()
        self._core = client.CoreV1Api()
        self._net = client.NetworkingV1Api()

    def _configure_client(self) -> None:
        try:
            config.load_incluster_config()
            logger.info("Kubernetes client: using in-cluster configuration")
        except ConfigException:
            path = self._settings.k8s_kubeconfig_path
            if path:
                config.load_kube_config(config_file=path)
                logger.info("Kubernetes client: loaded kubeconfig %s", path)
            else:
                config.load_kube_config()
                logger.info("Kubernetes client: loaded default kubeconfig")

    def submit(self, envelope: dict[str, Any]) -> Tuple[V1Job, SessionAccessDescriptor]:
        ns = self._settings.k8s_namespace
        workload = envelope["workload"]
        submission_id = envelope["submission_id"]

        if workload.get("needs_ingress") and not workload.get("needs_service"):
            raise ValueError("needs_ingress requires needs_service")

        user_id_label = normalize_user_id_label_value(envelope["user_id"])
        job_id_label = normalize_job_id_label_value(str(envelope["job_id"]))
        queue_name = self._settings.kueue_local_queue_for_workload_kind(str(workload["kind"]))

        job_name, svc_name, ing_name = resource_names_from_submission(submission_id)
        labels = base_labels_for_job(
            envelope,
            kueue_queue_name=queue_name,
            user_id_label_value=user_id_label,
            job_id_label_value=job_id_label,
        )
        ingress_path = ""
        if workload.get("needs_service"):
            ingress_path = ingress_path_for_workload(self._settings, workload, submission_id)
        disable_jupyter_token = (
            self._settings.k8s_ingress_auth_enabled
            and self._settings.k8s_ingress_auth_disable_jupyter_token
        )
        pod_template = build_pod_template(
            workload,
            labels,
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
            ingress_path=ingress_path,
            ingress_auth_disable_jupyter_token=disable_jupyter_token,
            desktop_shm_size=self._settings.k8s_desktop_shm_default,
        )

        ttl = workload.get("ttl_seconds_after_finished")
        job_spec = V1JobSpec(
            suspend=True,
            template=pod_template,
            ttl_seconds_after_finished=int(ttl) if ttl is not None else None,
        )

        job = V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=V1ObjectMeta(name=job_name, namespace=ns, labels=labels),
            spec=job_spec,
        )

        created = self._create_job(ns, job)
        owner_refs = job_owner_references(created.metadata)

        if workload.get("needs_service"):
            port = workload_container_port(workload)
            self._create_service(ns, svc_name, labels, port, owner_refs=owner_refs)

        if not workload.get("needs_ingress"):
            return created, SessionAccessDescriptor(public_url=None)

        host = (self._settings.k8s_ingress_host or "").strip()
        path = ingress_path_for_workload(self._settings, workload, submission_id)
        if not host:
            logger.warning(
                "needs_ingress but HAMMRLY_K8S_INGRESS_HOST is unset; no access_url or Ingress submission_id=%s",
                submission_id,
            )
            return created, SessionAccessDescriptor(public_url=None, path=path)

        desc = self._edge_strategy.apply(
            submitter=self,
            namespace=ns,
            ingress_name=ing_name,
            service_name=svc_name,
            host=host,
            path=path,
            submission_id=submission_id,
            owner_refs=owner_refs,
        )
        return created, desc

    def _create_job(self, ns: str, job: V1Job) -> V1Job:
        name = job.metadata.name
        try:
            out = self._batch.create_namespaced_job(namespace=ns, body=job)
            logger.info("Created Job %s/%s", ns, name)
            return out
        except ApiException as e:
            if e.status == 409:
                logger.info("Job already exists %s/%s", ns, name)
                return self._batch.read_namespaced_job(name=name, namespace=ns)
            logger.error("Job create failed status=%s reason=%s body=%s", e.status, e.reason, e.body)
            raise

    def _create_service(
        self,
        ns: str,
        name: str,
        selector_labels: dict[str, str],
        target_port: int,
        *,
        owner_refs: list[V1OwnerReference] | None = None,
    ) -> None:
        selector = {LABEL_SUBMISSION_ID: selector_labels[LABEL_SUBMISSION_ID]}
        svc = V1Service(
            api_version="v1",
            kind="Service",
            metadata=V1ObjectMeta(
                name=name,
                namespace=ns,
                labels=selector_labels,
                owner_references=owner_refs or None,
            ),
            spec=V1ServiceSpec(
                type=self._settings.k8s_service_type,
                selector=selector,
                ports=[
                    V1ServicePort(
                        name="http",
                        port=80,
                        target_port=target_port,
                        protocol="TCP",
                    ),
                ],
            ),
        )
        try:
            self._core.create_namespaced_service(namespace=ns, body=svc)
            logger.info("Created Service %s/%s (targetPort=%s)", ns, name, target_port)
        except ApiException as e:
            if e.status == 409:
                logger.info("Service already exists %s/%s", ns, name)
                return
            raise

    def _create_ingress(
        self,
        ns: str,
        name: str,
        service_name: str,
        host: str,
        path: str,
        *,
        owner_refs: list[V1OwnerReference] | None = None,
    ) -> None:
        ing_class = self._settings.k8s_ingress_class_name

        backend = V1IngressBackend(
            service=V1IngressServiceBackend(
                name=service_name,
                port=V1ServiceBackendPort(number=80),
            ),
        )
        path_rule = V1HTTPIngressPath(
            path=path,
            path_type="Prefix",
            backend=backend,
        )
        rule = V1IngressRule(
            host=host,
            http=V1HTTPIngressRuleValue(paths=[path_rule]),
        )

        ingress_spec = V1IngressSpec(
            ingress_class_name=ing_class or None,
            rules=[rule],
        )
        annotations: dict[str, str] = {}
        if self._settings.k8s_ingress_auth_enabled:
            annotations.update(self._settings.k8s_ingress_auth_annotations)

        ingress = V1Ingress(
            api_version="networking.k8s.io/v1",
            kind="Ingress",
            metadata=V1ObjectMeta(
                name=name,
                namespace=ns,
                annotations=annotations or None,
                owner_references=owner_refs or None,
            ),
            spec=ingress_spec,
        )
        try:
            self._net.create_namespaced_ingress(namespace=ns, body=ingress)
            logger.info("Created Ingress %s/%s host=%s path=%s", ns, name, host, path)
        except ApiException as e:
            if e.status == 409:
                logger.info("Ingress already exists %s/%s", ns, name)
                return
            raise
