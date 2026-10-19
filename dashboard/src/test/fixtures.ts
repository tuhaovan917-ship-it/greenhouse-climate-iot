import type {
  Alert,
  CommandActivity,
  DeviceConfig,
  DeviceState,
  Telemetry,
  TelemetryBucket,
  TelemetryHistoryByBucket,
} from '../types/api'

export const fixtureDeviceConfig: DeviceConfig = {
  mode: 'AUTO',
  tempOnC: 30,
  tempOffC: 28,
  humidityOnPct: 55,
  humidityOffPct: 65,
  lightOnLux: 300,
  lightOffLux: 700,
}

export const fixtureTelemetry: Telemetry = {
  id: 1248,
  deviceId: 'greenhouse-01',
  temperatureC: 28.6,
  humidityPct: 67.4,
  lightLux: 486,
  waterOk: true,
  receivedAt: '2026-10-17T02:42:18Z',
}

export const fixtureDeviceState: DeviceState = {
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

export const fixtureSensorFaultTelemetry: Telemetry = {
  ...fixtureTelemetry,
  id: 1249,
  temperatureC: null,
  waterOk: null,
}

export const fixtureNoWaterTelemetry: Telemetry = {
  ...fixtureTelemetry,
  id: 1250,
  waterOk: false,
}

export const fixtureOfflineState: DeviceState = {
  ...fixtureDeviceState,
  online: false,
  fan: false,
  lastSeenAt: '2026-10-17T02:36:11Z',
  updatedAt: '2026-10-17T02:36:26Z',
}

export const fixtureCommandHistory: CommandActivity[] = [
  {
    commandId: 'cmd-fixture-late',
    deviceId: 'greenhouse-01',
    device: 'fan',
    requestedOn: true,
    status: 'APPLIED',
    reason: null,
    requestedAt: '2026-10-17T02:40:00Z',
    completedAt: '2026-10-17T02:40:07Z',
    wasLate: true,
  },
  {
    commandId: 'cmd-fixture-rejected',
    deviceId: 'greenhouse-01',
    device: 'mist',
    requestedOn: true,
    status: 'REJECTED',
    reason: 'NO_WATER',
    requestedAt: '2026-10-17T02:35:00Z',
    completedAt: '2026-10-17T02:35:01Z',
  },
]

export const fixtureAlerts: Alert[] = [
  {
    id: 24,
    deviceId: 'greenhouse-01',
    code: 'NO_WATER',
    severity: 'CRITICAL',
    message: 'Nguồn nước đã cạn, bơm phun sương được khóa bởi failsafe.',
    active: false,
    startedAt: '2026-10-16T08:25:00Z',
    lastSeenAt: '2026-10-16T08:31:00Z',
    resolvedAt: '2026-10-16T08:32:00Z',
  },
  {
    id: 17,
    deviceId: 'greenhouse-01',
    code: 'OFFLINE',
    severity: 'CRITICAL',
    message: 'Không nhận được bản tin hợp lệ từ thiết bị trong 15 giây.',
    active: false,
    startedAt: '2026-10-15T03:10:00Z',
    lastSeenAt: '2026-10-15T03:12:00Z',
    resolvedAt: '2026-10-15T03:12:05Z',
  },
]

const fixtureHistoryTimes = [
  '2026-10-19T08:45:00Z',
  '2026-10-19T08:50:00Z',
  '2026-10-19T08:55:00Z',
  '2026-10-19T09:00:00Z',
]

const rawHistory = fixtureHistoryTimes.map<Telemetry>((receivedAt, index) => ({
  ...fixtureTelemetry,
  id: 1300 + index,
  temperatureC: index === 1 ? null : 27.5 + index * 0.4,
  humidityPct: 68 - index,
  lightLux: 420 + index * 30,
  receivedAt,
}))

function bucketHistory(bucket: TelemetryBucket['bucket']): TelemetryBucket[] {
  return fixtureHistoryTimes.map((bucketStart, index) => ({
    deviceId: 'greenhouse-01',
    bucketStart,
    bucket,
    sampleCount: 10,
    temperatureC: index === 1 ? null : 27.5 + index * 0.4,
    humidityPct: 68 - index,
    lightLux: 420 + index * 30,
    waterOk: true,
  }))
}

export const fixtureTelemetryHistoryByBucket: TelemetryHistoryByBucket = {
  raw: { bucket: 'raw', data: rawHistory },
  '1m': { bucket: '1m', data: bucketHistory('1m') },
  '5m': { bucket: '5m', data: bucketHistory('5m') },
  '1h': { bucket: '1h', data: bucketHistory('1h') },
}
