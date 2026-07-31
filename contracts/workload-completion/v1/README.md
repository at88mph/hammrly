# Workload completion contract (v1)

This contract defines the JSON manifest a workload container writes into its shared workspace when processing finishes.

The orchestrator exposes these environment variables to the workload container:

| Variable | Default | Purpose |
|----------|---------|---------|
| `HAMMRLY_WORKSPACE` | `/workspace` | Shared `emptyDir` mounted into init, workload, and sidecar containers. |
| `HAMMRLY_INPUT_DIR` | `/workspace/inputs` | Input files downloaded by the init container. |
| `HAMMRLY_OUTPUT_DIR` | `/workspace/outputs` | Recommended directory for processing products. |
| `HAMMRLY_COMPLETION_FILE` | `/workspace/hammrly-complete.json` | Success manifest path. |
| `HAMMRLY_ERROR_FILE` | `/workspace/hammrly-error.json` | Error manifest path. |

## Success manifest

Write a success manifest to `HAMMRLY_COMPLETION_FILE` after all output files are closed:

```json
{
  "schema_version": "1.0",
  "status": "complete",
  "finished_at": "2026-05-28T22:00:00Z",
  "outputs": [
    "outputs/result.fits",
    {
      "path": "outputs/plot.png",
      "destination_uri": "https://example.test/upload/plot.png",
      "media_type": "image/png"
    }
  ]
}
```

Relative output paths are resolved from `HAMMRLY_WORKSPACE`. If `destination_uri` is omitted, the sidecar uses the job's `workload.output_uri` as a destination prefix.

## Error manifest

Write an error manifest to `HAMMRLY_ERROR_FILE` when the workload cannot produce valid outputs:

```json
{
  "schema_version": "1.0",
  "status": "error",
  "finished_at": "2026-05-28T22:00:00Z",
  "code": "processing_failed",
  "message": "No sources detected"
}
```

When the output-watcher sidecar observes this file, it emits a structured log line
(`HAMMRLY_WORKLOAD_ERROR=…`) and exits nonzero. The orchestrator scrapes that line
(or the Job annotation `hammrly.io/workload-error` when present), persists a
`workload_error` submission event, and sets `submissions.status_detail` to
`"{code}: {message}"` so Query/Portal can surface the failure without kubectl.

## Helper script

`hammrly_runtime.py` is dependency-free and can be copied into an image or fetched over HTTP during image build.

Python usage:

```python
from hammrly_runtime import complete, fail

complete(outputs=["outputs/result.fits"])
fail(code="processing_failed", message="No sources detected")
```

CLI usage:

```bash
python /path/to/hammrly_runtime.py complete outputs/result.fits outputs/log.txt
python /path/to/hammrly_runtime.py fail processing_failed "No sources detected"
```

The helper writes JSON atomically by writing a temporary file next to the target and renaming it into place.
