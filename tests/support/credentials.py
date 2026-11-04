"""tests/support/credentials: Google credentials that never leave the process — a token minted on every refresh."""

from datetime import UTC, datetime, timedelta

from google.auth.credentials import CredentialsWithQuotaProject
from google.auth.exceptions import RefreshError


class FakeCredentials(CredentialsWithQuotaProject):
    """Starts expired; each refresh mints `token-<n>` valid for an hour, or fails when told to."""

    def __init__(self, quota_project: str | None = None, *, broken: bool = False) -> None:
        super().__init__()
        self._quota_project_id = quota_project
        self.refreshes = 0
        self.broken = broken

    def refresh(self, request: object) -> None:
        if self.broken:
            msg = "the token endpoint said no"
            raise RefreshError(msg)
        self.refreshes += 1
        self.token = f"token-{self.refreshes}"
        self.expiry = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)

    def with_quota_project(self, quota_project_id: str | None) -> FakeCredentials:
        return FakeCredentials(quota_project_id, broken=self.broken)
