"""Telemetry history queries with optional UTC-aligned bucketing (contract 3.2).

Bucketing is done in Python on purpose: `strftime` on SQLite and `date_trunc`
on PostgreSQL are not interchangeable, and v0.2 explicitly forbids
engine-specific SQL (database/README.md section 2). A MAX_SCAN_ROWS guard
keeps a wide range from pulling the whole table.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.config import settings
from app.models import TelemetryReading
from app.schemas import BUCKET_SECONDS, TelemetryBucket, TelemetryHistoryResponse, TelemetryOut

logger = logging.getLogger(__name__)


class ScanTooLargeError(ValueError):
    """Raised when a history query would exceed MAX_SCAN_ROWS."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def toUtc(value: datetime | None) -> datetime | None:
    """Normalise any datetime (aware or naive) to aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def bucketStartOf(moment: datetime, sizeSeconds: int) -> datetime:
    """Floor a UTC timestamp to the bucket start, aligned to the UTC epoch."""
    moment = toUtc(moment) or moment
    epochSeconds = int(moment.timestamp())
    floored = epochSeconds - (epochSeconds % sizeSeconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def parseQueryTime(value: str | None, fieldName: str) -> datetime | None:
    """Accept ISO8601 with or without trailing Z."""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{fieldName} phai la ISO8601, vi du 2026-10-15T10:00:00Z") from error
    return toUtc(parsed)


class TelemetryService:
    def __init__(self) -> None:
        self._recent: deque[TelemetryReading] = deque(maxlen=settings.telemetry_cache_size)

    # --- ingest side ---

    def remember(self, reading: TelemetryReading) -> None:
        self._recent.appendleft(reading)

    def latest(self) -> TelemetryReading | None:
        return self._recent[0] if self._recent else None

    # --- query side ---

    def history(
        self,
        session: Session,
        deviceId: str,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        desc: bool,
        bucket: str,
    ) -> TelemetryHistoryResponse:
        # Contract 3.2: filter range is [from, to).
        statement = select(TelemetryReading).where(TelemetryReading.device_id == deviceId)
        if start is not None:
            statement = statement.where(TelemetryReading.received_at >= start)
        if end is not None:
            statement = statement.where(TelemetryReading.received_at < end)
        statement = statement.order_by(
            TelemetryReading.received_at.desc() if desc else TelemetryReading.received_at.asc(),
            TelemetryReading.id.desc() if desc else TelemetryReading.id.asc(),
        )
        statement = statement.limit(settings.max_scan_rows)

        rows = list(session.exec(statement).all())
        if bucket == "raw":
            return TelemetryHistoryResponse(
                bucket="raw",
                data=[TelemetryOut.model_validate(row) for row in rows[:limit]],
            )
        return TelemetryHistoryResponse(bucket=bucket, data=self._aggregate(rows, bucket, limit))

    @staticmethod
    def _aggregate(
        rows: list[TelemetryReading], bucket: str, limit: int
    ) -> list[TelemetryBucket]:
        """Average numerics, keep the last non-null waterOk per bucket."""
        sizeSeconds = BUCKET_SECONDS[bucket]
        grouped: dict[datetime, list[TelemetryReading]] = {}
        for row in rows:
            grouped.setdefault(bucketStartOf(row.received_at, sizeSeconds), []).append(row)

        results: list[TelemetryBucket] = []
        for bucketStart, samples in grouped.items():
            samples.sort(key=lambda item: item.received_at)
            waterValues = [sample.water_ok for sample in samples if sample.water_ok is not None]
            results.append(
                TelemetryBucket(
                    device_id=samples[0].device_id,
                    bucket_start=bucketStart,
                    bucket=bucket,  # type: ignore[arg-type]
                    sample_count=len(samples),
                    temperature_c=_average([sample.temperature_c for sample in samples]),
                    humidity_pct=_average([sample.humidity_pct for sample in samples]),
                    light_lux=_average([sample.light_lux for sample in samples]),
                    water_ok=waterValues[-1] if waterValues else None,
                )
            )

        results.sort(key=lambda item: item.bucket_start, reverse=True)
        return results[:limit]

    def historyRange(self, start: datetime | None, end: datetime | None) -> timedelta | None:
        if start is None or end is None:
            return None
        return end - start


def _average(values: list[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 2)


telemetryService = TelemetryService()
