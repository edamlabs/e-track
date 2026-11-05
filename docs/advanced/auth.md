# Authentication

Every driver that leaves the process signs what it sends with one `Auth`, set in its configuration. One shape for all
of them: the OTLP driver's targets, the HTTP driver, and any driver you build on it.

| `type` | Sends | For |
|---|---|---|
| `none` | nothing | a local collector, a sidecar |
| `headers` | fixed headers, each a secret | API keys (`x-api-key`), tenant ids |
| `bearer` | `Authorization: Bearer <token>` | most APIs |
| `basic` | `Authorization: Basic <user:password>` | Langfuse, Grafana Cloud |
| `google` | a fresh OAuth token and `x-goog-user-project` | Cloud Trace, any Google API |

Picked by `type`, so it reads from the environment as JSON:

```bash
ETRACK_HTTP_AUTH='{"type": "bearer", "token": "…"}'
ETRACK_OTLP_TARGETS='{"grafana": {
  "endpoint": "https://otlp-gateway-prod-eu-west-2.grafana.net/otlp",
  "auth": {"type": "basic", "username": "123456", "password": "glc_…"}}}'
```

Or in code:

```python
from etrack.infra.config.auth import BasicAuth, BearerAuth, GoogleAuth, HeadersAuth
from pydantic import SecretStr

BearerAuth(token=SecretStr("…"))
GoogleAuth(quota_project="my-project")
```

Secrets stay masked in reprs, logs and errors; only the wire sees them. A target's fixed `headers` and its `auth` add
up: the auth's headers win where both name one.

## Google

`google` reads Application Default Credentials — a service account file in `GOOGLE_APPLICATION_CREDENTIALS`, your
`gcloud auth application-default login`, or the metadata server on Google Cloud — once, off the event loop, when the
driver opens. The token is refreshed off the loop before it expires, and a request refused with 401 is retried once
refreshed.

| `GoogleAuth` | default | |
|---|---|---|
| `scopes` | `cloud-platform` | the OAuth scopes asked for |
| `quota_project` | `""` | billed for the calls (`x-goog-user-project`); the Telemetry API requires one |

No credentials → `AuthError` when the driver opens, never at the first send. Install `e-track[auth]` (the `otel` and
`http` extras include it).

## Your own driver

`AuthSigner(auth)` is what the drivers use: `await signer.ready()` once, then `await signer.headers()` before each
request — or `signer.session()` for a library built on `requests`.
