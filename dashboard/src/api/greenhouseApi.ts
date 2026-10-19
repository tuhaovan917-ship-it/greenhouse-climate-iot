import type {
  AlertCode,
  AlertList,
  Bucket,
  CommandAccepted,
  CommandLogList,
  CommandRequest,
  ConfigPublished,
  ControlMode,
  DeviceConfig,
  DeviceState,
  Telemetry,
  TelemetryHistoryByBucket,
} from '../types/api'
import { apiRequest } from './httpClient'

interface HistoryQuery {
  deviceId: string
  bucket: Bucket
  from?: string
  to?: string
  limit?: number
  order?: 'asc' | 'desc'
}

interface AlertQuery {
  deviceId: string
  active?: boolean
  code?: AlertCode
  from?: string
  to?: string
  limit?: number
}

function withQuery(path: string, params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) {
      search.set(key, String(value))
    }
  })

  const query = search.toString()
  return query ? `${path}?${query}` : path
}

export function getLatestTelemetry(deviceId: string) {
  return apiRequest<Telemetry>(withQuery('/api/telemetry/latest', { deviceId }))
}

export function getDeviceState(deviceId: string) {
  return apiRequest<DeviceState>(withQuery('/api/state', { deviceId }))
}

export function getDeviceConfig(deviceId: string) {
  return apiRequest<DeviceConfig>(withQuery('/api/config', { deviceId }))
}

export function getTelemetryHistory<B extends Bucket>({
  deviceId,
  bucket,
  from,
  to,
  limit = 100,
  order = 'asc',
}: HistoryQuery & { bucket: B }): Promise<TelemetryHistoryByBucket[B]> {
  return apiRequest<TelemetryHistoryByBucket[B]>(
    withQuery('/api/telemetry', {
      deviceId,
      bucket,
      from,
      to,
      limit,
      order,
    }),
  )
}

export function getCommands(deviceId: string, limit = 50) {
  return apiRequest<CommandLogList>(
    withQuery('/api/commands', { deviceId, limit }),
  )
}

export function getAlerts({
  deviceId,
  active,
  code,
  from,
  to,
  limit = 50,
}: AlertQuery) {
  return apiRequest<AlertList>(
    withQuery('/api/alerts', {
      deviceId,
      active,
      code,
      from,
      to,
      limit,
    }),
  )
}

export function postCommand(request: CommandRequest) {
  return apiRequest<CommandAccepted>('/api/commands', {
    authenticated: true,
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function postDeviceConfig(deviceId: string, config: DeviceConfig) {
  return apiRequest<ConfigPublished>(
    withQuery('/api/config', { deviceId }),
    {
      authenticated: true,
      method: 'POST',
      body: JSON.stringify(config),
    },
  )
}

export function withMode(config: DeviceConfig, mode: ControlMode): DeviceConfig {
  return { ...config, mode }
}
