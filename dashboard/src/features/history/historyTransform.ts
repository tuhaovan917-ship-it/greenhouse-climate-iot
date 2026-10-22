import type {
  Telemetry,
  TelemetryBucket,
  TelemetryHistoryResponse,
} from '../../types/api'

export interface ChartPoint {
  timestampMs: number
  temperatureC: number | null
  humidityPct: number | null
  lightLux: number | null
}

function pointTimestamp(point: Telemetry | TelemetryBucket) {
  return 'receivedAt' in point ? point.receivedAt : point.bucketStart
}

export function normalizeTelemetryHistory(
  response: TelemetryHistoryResponse,
): ChartPoint[] {
  return response.data
    .map((point) => ({
      timestampMs: Date.parse(pointTimestamp(point)),
      temperatureC: point.temperatureC,
      humidityPct: point.humidityPct,
      lightLux: point.lightLux,
    }))
    .filter((point) => Number.isFinite(point.timestampMs))
    .sort((left, right) => left.timestampMs - right.timestampMs)
}
