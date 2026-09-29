from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import jwt

from apps.api.changetrace_api.config import get_settings

logger = logging.getLogger("changetrace.github.app")


def normalize_private_key(key_input: str | None) -> str | None:
    """Normalize private key from path, literal string, or environment variable with escaped newlines."""
    if not key_input:
        return None
    key_str = key_input.strip()
    # Check if key_input is a path to an existing file
    try:
        path = Path(key_str)
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    # Normalize escaped newlines
    if "\\n" in key_str and "\n" not in key_str:
        key_str = key_str.replace("\\n", "\n")
    return key_str


class GitHubAppService:
    """Manages GitHub App JWT authentication and installation access token lifecycle."""

    def __init__(
        self,
        app_id: str | None = None,
        private_key: str | None = None,
        redis_client: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.app_id = app_id or settings.github_app_id
        self.private_key = normalize_private_key(private_key or settings.github_app_private_key)
        self.environment = getattr(settings, "environment", "development")
        self._token_cache: dict[str, dict[str, Any]] = {}
        self.redis_client = redis_client
        if self.redis_client is None and getattr(settings, "redis_url", None):
            try:
                from redis import Redis
                self.redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
            except Exception:
                self.redis_client = None

    def is_configured(self) -> bool:
        return bool(self.app_id and self.private_key)

    def generate_jwt(self, expiration_seconds: int = 600) -> str:
        """Create an RS256 signed JWT for GitHub App authentication."""
        if not self.is_configured():
            raise ValueError("GitHub App ID and private key must be configured")
        if not self.private_key:
            raise ValueError("GitHub App private key is required")

        now = int(time.time())
        payload = {
            "iat": now - 60,  # 60s drift allowance
            "exp": now + expiration_seconds,
            "iss": self.app_id,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def get_installation_token(
        self,
        installation_id: str | int,
        client: httpx.Client | None = None,
        allow_mock: bool = False,
    ) -> str:
        """Fetch or return cached installation access token with multi-worker coordination and expiry tracking."""
        inst_id = str(installation_id)
        now = time.time()

        # 1. Check Redis cache first if configured
        if self.redis_client:
            try:
                redis_key = f"changetrace:github:token:{inst_id}"
                cached_token = self.redis_client.get(redis_key)
                if cached_token:
                    return cached_token
            except Exception as exc:
                logger.debug("Redis token lookup failed, falling back to local cache: %s", exc)

        # 2. Check local process cache with 5-minute safety buffer
        cached = self._token_cache.get(inst_id)
        if cached and cached["expires_at"] > now + 300:
            return cached["token"]

        # 3. Handle unconfigured state: disallow mock in production
        if not self.is_configured():
            if self.environment == "production" and not allow_mock:
                raise RuntimeError("GitHub App is unconfigured: app_id and private_key are required in production")
            token = f"ghs_mock_token_for_inst_{inst_id}"
            expires_at = now + 3600
            self._token_cache[inst_id] = {"token": token, "expires_at": expires_at}
            return token

        # 4. Request new token from GitHub API with retry handling
        jwt_token = self.generate_jwt()
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        url = f"https://api.github.com/app/installations/{inst_id}/access_tokens"

        close_client = False
        if client is None:
            client = httpx.Client(timeout=15.0)
            close_client = True

        try:
            max_retries = 2
            response = None
            for attempt in range(max_retries + 1):
                response = client.post(url, headers=headers)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < max_retries:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    time.sleep(min(retry_after, 5))
                    continue
                response.raise_for_status()
                break

            if response is None:
                raise RuntimeError("GitHub token request failed: no response")

            data = response.json()
            token = data["token"]

            # Parse GitHub's expires_at timestamp
            if "expires_at" in data:
                try:
                    exp_dt = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
                    expires_at = exp_dt.timestamp()
                except Exception:
                    expires_at = now + 3500
            else:
                expires_at = now + 3500

            # Store in local process cache
            self._token_cache[inst_id] = {"token": token, "expires_at": expires_at}

            # Store in shared Redis cache if available
            if self.redis_client:
                try:
                    ttl_seconds = max(60, int(expires_at - now - 60))
                    redis_key = f"changetrace:github:token:{inst_id}"
                    self.redis_client.setex(redis_key, ttl_seconds, token)
                except Exception as exc:
                    logger.debug("Failed to cache GitHub token in Redis: %s", exc)

            return token
        finally:
            if close_client:
                client.close()

    def clear_cache(self) -> None:
        self._token_cache.clear()
        if self.redis_client:
            try:
                # Flush cached tokens in Redis
                for key in self.redis_client.scan_iter("changetrace:github:token:*"):
                    self.redis_client.delete(key)
            except Exception:
                pass
