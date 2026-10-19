import { useCallback, useEffect, useState } from 'react'
import {
  getAlerts,
  getCommands,
  getDeviceConfig,
  getDeviceState,
  getLatestTelemetry,
  getTelemetryHistory,
  postCommand,
  postDeviceConfig,
  withMode,
} from '../api/greenhouseApi'
import { dashboardConfig } from '../api/config'
import { createPendingCommand, mergeCommandResult } from '../features/control/commandState'
import type {
  Alert,
  CommandActivity,
  CommandRequest,
  ConfigPublished,
  ControlMode,
  DeviceConfig,
  DeviceState,
  Telemetry,
  TelemetryHistoryByBucket,
  WsMessage,
} from '../types/api'

type LoadStatus = 'idle' | 'loading' | 'ready' | 'error'
export type RealtimeStatus = 'connecting' | 'connected' | 'polling'

interface UseGreenhouseDashboardOptions {
  deviceId: string
  enabled: boolean
}

const pollingIntervalMs = 5_000
const reconnectDelayMs = 3_000
const pingIntervalMs = 10_000
const historyRefreshMs = 30_000

function getHistoryStart() {
  return new Date(Date.now() - 24 * 60 * 60 * 1_000).toISOString()
}

async function loadHistory(deviceId: string): Promise<TelemetryHistoryByBucket> {
  const from = getHistoryStart()
  const [raw, oneMinute, fiveMinutes, oneHour] = await Promise.all([
    getTelemetryHistory({ deviceId, bucket: 'raw', from }),
    getTelemetryHistory({ deviceId, bucket: '1m', from }),
    getTelemetryHistory({ deviceId, bucket: '5m', from }),
    getTelemetryHistory({ deviceId, bucket: '1h', from }),
  ])

  return {
    raw,
    '1m': oneMinute,
    '5m': fiveMinutes,
    '1h': oneHour,
  }
}

function upsertAlert(current: Alert[], incoming: Alert) {
  return [incoming, ...current.filter((alert) => alert.id !== incoming.id)]
}

function upsertRawTelemetry(
  history: TelemetryHistoryByBucket,
  telemetry: Telemetry,
): TelemetryHistoryByBucket {
  const latest = [
    telemetry,
    ...history.raw.data.filter((item) => item.id !== telemetry.id),
  ]
    .sort((left, right) => Date.parse(right.receivedAt) - Date.parse(left.receivedAt))
    .slice(0, 100)
    .reverse()

  return {
    ...history,
    raw: { bucket: 'raw', data: latest },
  }
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Không thể kết nối Backend.'
}

export function useGreenhouseDashboard({
  deviceId,
  enabled,
}: UseGreenhouseDashboardOptions) {
  const [status, setStatus] = useState<LoadStatus>(enabled ? 'loading' : 'idle')
  const [realtimeStatus, setRealtimeStatus] = useState<RealtimeStatus>('connecting')
  const [error, setError] = useState<string | null>(null)
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null)
  const [deviceState, setDeviceState] = useState<DeviceState | null>(null)
  const [history, setHistory] = useState<TelemetryHistoryByBucket | null>(null)
  const [config, setConfig] = useState<DeviceConfig | null>(null)
  const [commands, setCommands] = useState<CommandActivity[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])

  const loadInitial = useCallback(async () => {
    if (!enabled) {
      return
    }

    setStatus('loading')
    setError(null)

    try {
      const [
        latestTelemetry,
        latestState,
        latestHistory,
        latestConfig,
        commandList,
        alertList,
      ] = await Promise.all([
        getLatestTelemetry(deviceId),
        getDeviceState(deviceId),
        loadHistory(deviceId),
        getDeviceConfig(deviceId),
        getCommands(deviceId),
        getAlerts({ deviceId }),
      ])

      setTelemetry(latestTelemetry)
      setDeviceState(latestState)
      setHistory(latestHistory)
      setConfig(latestConfig)
      setCommands(commandList.data)
      setAlerts(alertList.data)
      setStatus('ready')
    } catch (loadError) {
      setError(getErrorMessage(loadError))
      setStatus('error')
    }
  }, [deviceId, enabled])

  const refreshSnapshot = useCallback(async () => {
    const [latestTelemetry, latestState, alertList] = await Promise.all([
      getLatestTelemetry(deviceId),
      getDeviceState(deviceId),
      getAlerts({ deviceId }),
    ])

    setTelemetry(latestTelemetry)
    setDeviceState(latestState)
    setAlerts(alertList.data)
  }, [deviceId])

  const refreshHistory = useCallback(async () => {
    setHistory(await loadHistory(deviceId))
  }, [deviceId])

  useEffect(() => {
    const loadTimer = window.setTimeout(() => {
      void loadInitial()
    }, 0)

    return () => window.clearTimeout(loadTimer)
  }, [loadInitial])

  useEffect(() => {
    if (!enabled || status !== 'ready') {
      return
    }

    let stopped = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let pollingTimer: number | null = null
    let pingTimer: number | null = null

    function stopPolling() {
      if (pollingTimer !== null) {
        window.clearInterval(pollingTimer)
        pollingTimer = null
      }
    }

    function startPolling() {
      if (pollingTimer !== null || stopped) {
        return
      }

      setRealtimeStatus('polling')
      void refreshSnapshot().catch(() => undefined)
      pollingTimer = window.setInterval(() => {
        void refreshSnapshot().catch(() => undefined)
      }, pollingIntervalMs)
    }

    function handleMessage(event: MessageEvent<string>) {
      let message: WsMessage

      try {
        message = JSON.parse(event.data) as WsMessage
      } catch {
        return
      }

      if (message.type === 'telemetry') {
        setTelemetry(message.data)
        setHistory((current) => current ? upsertRawTelemetry(current, message.data) : current)
        return
      }

      if (message.type === 'state') {
        setDeviceState(message.data)
        return
      }

      if (message.type === 'command_result') {
        setCommands((current) =>
          mergeCommandResult(current, message.data, new Date().toISOString()),
        )
        return
      }

      if (message.type === 'alert') {
        setAlerts((current) => upsertAlert(current, message.data))
      }
    }

    function connect() {
      if (stopped) {
        return
      }

      setRealtimeStatus('connecting')
      const url = new URL(dashboardConfig.wsUrl)
      url.searchParams.set('deviceId', deviceId)
      socket = new WebSocket(url)

      socket.onopen = () => {
        if (stopped) {
          socket?.close()
          return
        }

        setRealtimeStatus('connected')
        stopPolling()
        void refreshSnapshot().catch(() => undefined)

        pingTimer = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send('ping')
          }
        }, pingIntervalMs)
      }

      socket.onmessage = handleMessage
      socket.onerror = () => socket?.close()
      socket.onclose = () => {
        if (pingTimer !== null) {
          window.clearInterval(pingTimer)
          pingTimer = null
        }

        if (stopped) {
          return
        }

        startPolling()
        reconnectTimer = window.setTimeout(connect, reconnectDelayMs)
      }
    }

    connect()
    const historyTimer = window.setInterval(() => {
      void refreshHistory().catch(() => undefined)
    }, historyRefreshMs)

    return () => {
      stopped = true
      stopPolling()
      window.clearInterval(historyTimer)

      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
      }
      if (pingTimer !== null) {
        window.clearInterval(pingTimer)
      }

      socket?.close()
    }
  }, [deviceId, enabled, refreshHistory, refreshSnapshot, status])

  const sendCommand = useCallback(async (request: CommandRequest) => {
    const accepted = await postCommand(request)
    const pending = createPendingCommand(request, accepted, new Date().toISOString())
    setCommands((current) => [pending, ...current])
  }, [])

  const publishMode = useCallback(async (mode: ControlMode): Promise<ConfigPublished> => {
    if (!config) {
      throw new Error('Chưa tải được cấu hình thiết bị.')
    }

    const published = await postDeviceConfig(deviceId, withMode(config, mode))
    setConfig(published.config)
    return published
  }, [config, deviceId])

  return {
    status,
    realtimeStatus,
    error,
    telemetry,
    deviceState,
    history,
    config,
    commands,
    alerts,
    retry: loadInitial,
    sendCommand,
    publishMode,
  }
}
