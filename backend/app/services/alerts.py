"""Alert derivation with de-duplication (database/SCHEMA.md v0.2 section 6).

Rules
-----
- Same `device_id + code` with an active row -> update `last_seen_at` only.
- Condition cleared -> `active=false` + `resolved_at`.
- Condition returns after being resolved -> insert a brand new episode.
- Demo mode closes alerts immediately; the hardened build needs 3 good samples
  in a row (`ALERT_CLEAR_SAMPLES`).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.models import (
    ALERT_MESSAGES,
    ALERT_SEVERITY_BY_CODE,
    Alert,
    utcNow,
)

logger = logging.getLogger(__name__)

# 1 = demo behaviour (close immediately). Raise for the final report build.
ALERT_CLEAR_SAMPLES = 1

NO_WATER = "NO_WATER"
SENSOR_FAULT = "SENSOR_FAULT"
OFFLINE = "OFFLINE"


@dataclass
class AlertEpisode:
    """Tracks how many consecutive healthy samples we have seen."""

    counters: dict[str, int] = field(default_factory=dict)

    def healthy(self, code: str) -> None:
        self.counters[code] = self.counters.get(code, 0) + 1

    def unhealthy(self, code: str) -> None:
        self.counters[code] = 0

    def isCleared(self, code: str) -> bool:
        return self.counters.get(code, 0) >= ALERT_CLEAR_SAMPLES


class AlertService:
    def __init__(self) -> None:
        self._episodes = AlertEpisode()
        # Ingest runs in a threadpool, so two messages arriving together could
        # both decide to open the same alert. Serialise the read-modify-write.
        self._lock = threading.Lock()

    # --- public API ---

    def openOrRefresh(self, session: Session, deviceId: str, code: str) -> Alert:
        """Mark the condition as currently true."""
        with self._lock:
            self._episodes.unhealthy(code)
            alert = self._findActive(session, deviceId, code)
            now = utcNow()
            if alert is not None:
                alert.last_seen_at = now
                return alert
            alert = Alert(
                device_id=deviceId,
                code=code,
                severity=ALERT_SEVERITY_BY_CODE.get(code, "WARNING"),
                message=ALERT_MESSAGES.get(code, code),
                active=True,
                started_at=now,
                last_seen_at=now,
            )
            session.add(alert)
            logger.warning("alert opened: %s %s", deviceId, code)
            return alert

    def clearIfHealthy(self, session: Session, deviceId: str, code: str) -> Alert | None:
        """Close the active alert once the condition stayed healthy long enough."""
        with self._lock:
            self._episodes.healthy(code)
            if not self._episodes.isCleared(code):
                return None
            alert = self._findActive(session, deviceId, code)
            if alert is None:
                return None
            now = utcNow()
            alert.active = False
            alert.resolved_at = now
            alert.last_seen_at = now
            logger.info("alert resolved: %s %s", deviceId, code)
            return alert

    def activeAlerts(self, session: Session, deviceId: str) -> list[Alert]:
        statement = (
            select(Alert)
            .where(Alert.device_id == deviceId, Alert.active.is_(True))  # type: ignore[attr-defined]
            .order_by(Alert.started_at.desc(), Alert.id.desc())
        )
        return list(session.exec(statement).all())

    # --- helpers ---

    @staticmethod
    def _findActive(session: Session, deviceId: str, code: str) -> Alert | None:
        statement = (
            select(Alert)
            .where(Alert.device_id == deviceId, Alert.code == code, Alert.active.is_(True))  # type: ignore[attr-defined]
            .order_by(Alert.started_at.desc(), Alert.id.desc())
        )
        return session.exec(statement).first()


alertService = AlertService()
