export type ControlMode = 'AUTO' | 'MANUAL'
export type DeviceName = 'fan' | 'mist' | 'lamp'
export type CommandStatus = 'PENDING' | 'APPLIED' | 'REJECTED' | 'TIMEOUT'
export type TerminalCommandResult = Exclude<CommandStatus, 'PENDING'>
export type Bucket = 'raw' | '1m' | '5m' | '1h'
export type AggregateBucket = Exclude<Bucket, 'raw'>
export type AlertCode = 'NO_WATER' | 'SENSOR_FAULT' | 'OFFLINE'
export type AlertSeverity = 'INFO' | 'WARNING' | 'CRITICAL'

export interface Telemetry {
  id: number
  deviceId: string
  temperatureC: number | null
  humidityPct: number | null
  lightLux: number | null
  waterOk: boolean | null
  receivedAt: string
}

export interface TelemetryBucket {
  deviceId: string
  bucketStart: string
  bucket: AggregateBucket
  sampleCount: number
  temperatureC: number | null
  humidityPct: number | null
  lightLux: number | null
  waterOk: boolean | null
}

export type TelemetryHistoryResponse =
  | { bucket: 'raw'; data: Telemetry[] }
  | { bucket: AggregateBucket; data: TelemetryBucket[] }

export interface TelemetryHistoryByBucket {
  raw: { bucket: 'raw'; data: Telemetry[] }
  '1m': { bucket: '1m'; data: TelemetryBucket[] }
  '5m': { bucket: '5m'; data: TelemetryBucket[] }
  '1h': { bucket: '1h'; data: TelemetryBucket[] }
}

export interface DeviceState {
  deviceId: string
  mode: ControlMode
  fan: boolean
  mist: boolean
  lamp: boolean
  failsafeActive: boolean
  online: boolean
  lastSeenAt: string | null
  lastCommandId: string | null
  lastCommandResult: 'APPLIED' | 'REJECTED' | null
  reason?: string | null
  updatedAt: string
}

export interface DeviceConfig {
  mode: ControlMode
  tempOnC: number
  tempOffC: number
  humidityOnPct: number
  humidityOffPct: number
  lightOnLux: number
  lightOffLux: number
}

export interface CommandLog {
  commandId: string
  deviceId: string
  device: DeviceName
  requestedOn: boolean
  status: CommandStatus
  reason?: string | null
  requestedAt: string
  completedAt: string | null
}

export interface CommandRequest {
  deviceId: string
  device: DeviceName
  on: boolean
}

export interface CommandAccepted {
  commandId: string
  status: 'PENDING'
}

export interface CommandLogList {
  data: CommandLog[]
}

export interface CommandActivity extends CommandLog {
  wasLate?: boolean
}

export interface ConfigPublished {
  status: 'PUBLISHED'
  config: DeviceConfig
}

export interface Alert {
  id: number
  deviceId: string
  code: AlertCode
  severity: AlertSeverity
  message: string
  active: boolean
  startedAt: string
  lastSeenAt: string
  resolvedAt: string | null
}

export interface AlertList {
  data: Alert[]
}

export interface CommandResultData {
  commandId: string
  result: TerminalCommandResult
  reason?: string | null
  wasLate?: boolean
}

export type WsMessage =
  | { type: 'telemetry'; data: Telemetry }
  | { type: 'state'; data: DeviceState }
  | { type: 'command_result'; data: CommandResultData }
  | { type: 'alert'; data: Alert }
