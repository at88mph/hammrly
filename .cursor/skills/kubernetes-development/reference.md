# kubernetes-development reference

## `hammrly_orchestrator.k8s` files

| File | Types / APIs |
|------|----------------|
| `submitter.py` | `KubernetesSubmitter`, `V1Job`, `V1Service`, `V1Ingress`, `BatchV1Api`, `CoreV1Api`, `NetworkingV1Api` |
| `pod_spec.py` | `V1PodTemplateSpec`, `V1PodSpec`, `V1Container`, `V1Volume`, `V1Affinity`, `V1ResourceRequirements`, security contexts |
| `probes.py` | `V1Probe`, `V1HTTPGetAction`, `V1TCPSocketAction`, `V1ExecAction`, `V1ContainerPort` |
| `labels.py` | Label constants, `KUEUE_LOCAL_QUEUE_LABEL`, name derivation |
| `edge_binding.py` | `SessionAccessDescriptor`, ingress strategies |
| `job_state.py` | `V1Job` status mapping |
| `job_watch.py` | `Watch`, `BatchV1Api`, `CoreV1Api` |
| `pod_watch.py` | `Watch`, `CoreV1Api`, `V1Pod` |
| `drift_reconcile.py` | `BatchV1Api` LIST |
| `workload_error.py` | `V1Job`, `CoreV1Api` log reads |

## Typed models commonly imported

```
V1Job, V1JobSpec, V1Pod, V1PodSpec, V1PodTemplateSpec, V1ObjectMeta,
V1Container, V1Service, V1ServiceSpec, V1Ingress, V1IngressSpec,
V1OwnerReference, V1ResourceRequirements, V1Probe, V1Volume, V1VolumeMount,
V1PodSecurityContext, V1SecurityContext, V1Affinity, V1Toleration
```

## Kueue (as implemented)

| Mechanism | Detail |
|-----------|--------|
| Admission | `spec.suspend: true` on create |
| Queue selection | Label `kueue.x-k8s.io/queue-name` on Job metadata |
| Config | `kueue_local_queue_default`, `kueue_queue_<kind>` on `Settings` |
| Not done | Unsuspend Job in orchestrator; Kueue Workload CRD via `CustomObjectsApi` |

## External documentation

- Python client: https://github.com/kubernetes-client/python
- Client models (e.g. `V1Job`): generated under `kubernetes.client` for installed package version
- Kueue labels: https://kueue.sigs.k8s.io/docs/reference/labels-and-annotations
- Job suspension: Kubernetes `batch/v1` Job `spec.suspend` (cluster version must support it)

## Persistence touchpoints

Job create/watch updates submission rows (`k8s_job_name`, `k8s_namespace`, `k8s_job_uid`, `k8s_resource_version`, status). Implementation: `hammrly_orchestrator.persistence.repository.SubmissionRepository` (imports `V1Job` where needed).
