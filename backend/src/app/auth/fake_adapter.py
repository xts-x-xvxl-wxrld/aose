from __future__ import annotations

from app.auth.types import AuthIdentity
from app.config import Settings


class FakeAuthAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def authenticate(self, bearer_token: str | None) -> AuthIdentity:
        subject = self._subject_from_token(bearer_token)
        return AuthIdentity(
            external_auth_subject=subject,
            email=self._settings.fake_auth_email,
            display_name=self._settings.fake_auth_display_name,
        )

    def _subject_from_token(self, bearer_token: str | None) -> str:
        if bearer_token:
            return bearer_token.strip()
        return self._settings.fake_auth_subject
