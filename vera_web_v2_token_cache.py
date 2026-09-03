"""Short-lived cache for Supabase access-token verification.

Every Web V2 data request still reloads the employee from PostgreSQL.  Only the
remote Supabase ``/auth/v1/user`` result is reused briefly, which removes a
request storm immediately after login without making account/permission
changes stale.
"""
from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
from threading import Condition
import time
from typing import Callable


class VerifiedTokenCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = 30.0,
        max_entries: int = 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = max(1.0, float(ttl_seconds))
        self._max_entries = max(1, int(max_entries))
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._loading: set[str] = set()
        self._condition = Condition()

    @staticmethod
    def _key(token: str) -> str:
        # Do not retain bearer tokens in process memory longer than the active
        # request.  A digest is sufficient as the cache key.
        return sha256(token.encode("utf-8")).hexdigest()

    def _read_locked(self, key: str, now: float) -> str | None:
        cached = self._entries.get(key)
        if cached is None:
            return None
        expires_at, auth_uid = cached
        if expires_at <= now:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return auth_uid

    def remember(self, token: str, auth_uid: str) -> None:
        token = str(token or "").strip()
        auth_uid = str(auth_uid or "").strip()
        if not token or not auth_uid:
            return
        key = self._key(token)
        with self._condition:
            self._entries[key] = (self._clock() + self._ttl_seconds, auth_uid)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
            self._condition.notify_all()

    def get_or_load(self, token: str, loader: Callable[[], str]) -> str:
        """Return a verified UID, coalescing concurrent checks for one token."""
        key = self._key(token)
        with self._condition:
            while True:
                cached = self._read_locked(key, self._clock())
                if cached is not None:
                    return cached
                if key not in self._loading:
                    self._loading.add(key)
                    break
                self._condition.wait()

        try:
            auth_uid = str(loader() or "").strip()
            if not auth_uid:
                raise ValueError("Token verifier returned an empty user id")
        except BaseException:
            with self._condition:
                self._loading.discard(key)
                self._condition.notify_all()
            raise

        with self._condition:
            self._entries[key] = (self._clock() + self._ttl_seconds, auth_uid)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
            self._loading.discard(key)
            self._condition.notify_all()
        return auth_uid
