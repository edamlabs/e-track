# Cloud Trace

Google Cloud Trace ingests OpenTelemetry through the Telemetry API: point the OTLP driver at it and sign with Google's
credentials. No other driver is needed. Install `e-track[otel]`.

```bash
ETRACK_OTLP_TARGETS='{"cloudtrace": {
  "endpoint": "https://telemetry.googleapis.com",
  "auth": {"type": "google", "quota_project": "my-project"}}}'
```

| Needs | |
|---|---|
| APIs | `telemetry.googleapis.com` and `cloudtrace.googleapis.com` enabled on the project — trace data is dropped otherwise |
| roles | Cloud Telemetry Writer (`roles/telemetry.writer`) on the project; Service Usage Consumer (`roles/serviceusage.serviceUsageConsumer`) on the quota project |
| credentials | Application Default Credentials → [Authentication](../advanced/auth.md#google) |
| endpoint | global `https://telemetry.googleapis.com`, or regional `https://telemetry.REGION.rep.googleapis.com` |

Limits that bound what a span may carry (Telemetry API, 2026-11-04): attribute keys 512 bytes, values 64 KiB, 1024
attributes per span, span names 1024 bytes; spans are kept 30 days. A run's inputs and outputs travel as attributes: keep
`redact` tight on large payloads.

There is no Cloud Trace emulator. Locally, any OpenTelemetry collector stands in for it — what reaches the collector is
what reaches Cloud Trace; the Google signing is tested against a local server with stand-in credentials.

Everything else about the driver → [OpenTelemetry](opentelemetry.md).
