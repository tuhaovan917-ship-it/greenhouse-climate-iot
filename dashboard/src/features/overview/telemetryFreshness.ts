import type { Telemetry } from '../../types/api'

export const telemetryStaleAfterMs = 10_000

export function isTelemetryStale(
  telemetry: Telemetry | null,
  online: boolean,
  nowMs = Date.now(),
) {
  if (!online || telemetry === null) {
    return false
  }

  const receivedAtMs = Date.parse(telemetry.receivedAt)
  return !Number.isFinite(receivedAtMs) || nowMs - receivedAtMs > telemetryStaleAfterMs
}
