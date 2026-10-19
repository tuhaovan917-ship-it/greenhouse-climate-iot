import type {
  AggregateBucket,
  DeviceState,
  Telemetry,
  TelemetryBucket,
  TelemetryHistoryByBucket,
} from '../types/api'

export const mockTelemetry: Telemetry = {
  id: 1248,
  deviceId: 'greenhouse-01',
  temperatureC: 28.6,
  humidityPct: 67.4,
  lightLux: 486,
  waterOk: true,
  receivedAt: '2026-10-17T02:42:18Z',
}

export const mockDeviceState: DeviceState = {
  deviceId: 'greenhouse-01',
  mode: 'AUTO',
  fan: true,
  mist: false,
  lamp: false,
  failsafeActive: false,
  online: true,
  lastSeenAt: '2026-10-17T02:42:18Z',
  lastCommandId: null,
  lastCommandResult: null,
  reason: null,
  updatedAt: '2026-10-17T02:42:18Z',
}

export const mockSensorFaultTelemetry: Telemetry = {
  ...mockTelemetry,
  id: 1249,
  temperatureC: null,
  waterOk: null,
}

export const mockNoWaterTelemetry: Telemetry = {
  ...mockTelemetry,
  id: 1250,
  waterOk: false,
}

export const mockOfflineState: DeviceState = {
  ...mockDeviceState,
  online: false,
  fan: false,
  lastSeenAt: '2026-10-17T02:36:11Z',
  updatedAt: '2026-10-17T02:36:26Z',
}

const historyEndMs = Date.parse('2026-10-19T09:00:00Z')
const historyPointCount = 24

function rounded(value: number, digits = 1) {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

function buildRawHistory(): Telemetry[] {
  return Array.from({ length: historyPointCount }, (_, index) => ({
    id: 2000 - index,
    deviceId: 'greenhouse-01',
    temperatureC:
      index === 7 || index === 8
        ? null
        : rounded(27.4 + Math.sin(index / 3) * 1.6 + index * 0.025),
    humidityPct:
      index === 14
        ? null
        : rounded(69.2 - Math.sin(index / 3.4) * 4.8 - index * 0.08),
    lightLux:
      index === 18
        ? null
        : Math.round(430 + Math.cos(index / 2.8) * 125 - index * 3.5),
    waterOk: index === 11 ? null : true,
    receivedAt: new Date(historyEndMs - index * 30_000).toISOString(),
  }))
}

const bucketDurationMs: Record<AggregateBucket, number> = {
  '1m': 60_000,
  '5m': 5 * 60_000,
  '1h': 60 * 60_000,
}

function buildBucketHistory(bucket: AggregateBucket): TelemetryBucket[] {
  const bucketOffset = bucket === '1m' ? 0 : bucket === '5m' ? 0.4 : 0.9
  const samplesPerBucket = bucket === '1m' ? 2 : bucket === '5m' ? 10 : 120

  return Array.from({ length: historyPointCount }, (_, index) => ({
    deviceId: 'greenhouse-01',
    bucketStart: new Date(
      historyEndMs - index * bucketDurationMs[bucket],
    ).toISOString(),
    bucket,
    sampleCount: samplesPerBucket - (index % 4 === 0 ? 1 : 0),
    temperatureC:
      index === 7 || index === 8
        ? null
        : rounded(27.2 + bucketOffset + Math.sin(index / 3.1) * 1.8),
    humidityPct:
      index === 14
        ? null
        : rounded(68.8 - bucketOffset - Math.sin(index / 3.5) * 5.2),
    lightLux:
      index === 18
        ? null
        : Math.round(440 + bucketOffset * 25 + Math.cos(index / 2.9) * 135),
    waterOk: index === 11 ? null : true,
  }))
}

export const mockTelemetryHistoryByBucket: TelemetryHistoryByBucket = {
  raw: { bucket: 'raw', data: buildRawHistory() },
  '1m': { bucket: '1m', data: buildBucketHistory('1m') },
  '5m': { bucket: '5m', data: buildBucketHistory('5m') },
  '1h': { bucket: '1h', data: buildBucketHistory('1h') },
}
