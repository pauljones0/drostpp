"""Model tier routing, per-role overrides, cooldowns, and provider failover."""

from __future__ import annotations

import threading
import time

from .config import RoutingConfig
from .models import ErrorKind, RouteTarget


class ModelRouter:
    """Resolves ordered provider/model routes for a task and manages transient/quota cooldowns."""

    def __init__(self, config: RoutingConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._cooldown_until: dict[tuple[str, str], float] = {}

    def resolve_routes(
        self,
        *,
        role: str,
        tier: str,
        now: float | None = None,
    ) -> list[RouteTarget]:
        """Return candidate routes ordered by tier/role preference, skipping routes in active cooldown."""
        effective_tier = self.config.role_overrides.get(role, tier) or "default"
        candidates = list(
            self.config.tiers.get(effective_tier)
            or self.config.tiers.get("default")
            or [RouteTarget(provider="codex", model="", tier=effective_tier)]
        )
        ts = time.monotonic() if now is None else now
        available: list[RouteTarget] = []
        cooling: list[tuple[float, RouteTarget]] = []
        with self._lock:
            for target in candidates:
                key = (target.provider, target.model)
                until = self._cooldown_until.get(key, 0.0)
                if until <= ts:
                    available.append(target)
                else:
                    cooling.append((until, target))
        if available:
            return available
        # If every route is cooling down, fall back to earliest expiring route so callers see clear progress/errors.
        cooling.sort(key=lambda item: item[0])
        return [item[1] for item in cooling]

    def record_outcome(self, target: RouteTarget, error_kind: ErrorKind, *, now: float | None = None) -> None:
        key = (target.provider, target.model)
        ts = time.monotonic() if now is None else now
        with self._lock:
            if error_kind == ErrorKind.NONE:
                self._cooldown_until.pop(key, None)
            elif error_kind in (ErrorKind.QUOTA, ErrorKind.TRANSIENT):
                multiplier = 2.0 if error_kind == ErrorKind.QUOTA else 1.0
                self._cooldown_until[key] = ts + self.config.cooldown_seconds * multiplier

    def is_cooling_down(self, target: RouteTarget, *, now: float | None = None) -> bool:
        ts = time.monotonic() if now is None else now
        with self._lock:
            return self._cooldown_until.get((target.provider, target.model), 0.0) > ts
