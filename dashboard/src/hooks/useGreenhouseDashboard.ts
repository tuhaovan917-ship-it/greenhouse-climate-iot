import { useCallback, useEffect, useRef, useState } from 'react'
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
import {
  createPendingCommand,
  mergeCommandResult,
  reconcileCommandSnapshot,
} from '../features/control/commandState'
import {
  defaultHistoryQuery,
  getHistoryBounds,
  type HistoryQuery,
} from '../features/history/historyQuery'
import type {
  Alert,
  CommandActivity,
  CommandRequest,
  ConfigPublished,
  ControlMode,
  DeviceConfig,
  DeviceState,
  Telemetry,
  TelemetryHistoryResponse,
  CommandResultData,
  WsMessage,
} from '../types/api'

type LoadStatus = 'idle' | 'loading' | 'ready' | 'error'
export type RealtimeStatus = 'connecting' | 'connected' | 'polling'

interface UseGreenhouseDashboardOptions {
  deviceId: string
  enabled: boolean
}

const pollingIntervalMs = 5_000
const pendingCommandSyncMs = 1_000
const reconnectDelayMs = 3_000
const historyRefreshMs = 30_000
const maxBufferedCommandResults = 100

interface BufferedCommandResult {
  data: CommandResultData
  receivedAt: string
}

function upsertAlert(current: Alert[], incoming: Alert) {
  return [incoming, ...current.filter((alert) => alert.id !== incoming.id)]
}

function upsertRawTelemetry(
  history: TelemetryHistoryResponse,
  telemetry: Telemetry,
): TelemetryHistoryResponse {
  if (history.bucket !== 'raw') {
    return history
  }

  const latest = [
    telemetry,
    ...history.data.filter((item) => item.id !== telemetry.id),
  ]
    .sort((left, right) => Date.parse(right.receivedAt) - Date.parse(left.receivedAt))
    .slice(0, 100)
    .reverse()

  return { bucket: 'raw', data: latest }
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
  const [history, setHistory] = useState<TelemetryHistoryResponse | null>(null)
  const [historyQuery, setHistoryQuery] = useState<HistoryQuery>(defaultHistoryQuery)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [config, setConfig] = useState<DeviceConfig | null>(null)
  const [commands, setCommands] = useState<CommandActivity[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const historyRequestId = useRef(0)
  const knownCommandIds = useRef(new Set<string>())
  const bufferedCommandResults = useRef(new Map<string, BufferedCommandResult>())

  const reconcileCommands = useCallback((incoming: CommandActivity[]) => {
    incoming.forEach((command) => knownCommandIds.current.add(command.commandId))
    setCommands((current) => reconcileCommandSnapshot(current, incoming))
  }, [])

  const refreshCommands = useCallback(async () => {
    const commandList = await getCommands(deviceId)
    reconcileCommands(commandList.data)
  }, [deviceId, reconcileCommands])

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
        latestConfig,
        commandList,
        alertList,
      ] = await Promise.all([
        getLatestTelemetry(deviceId),
        getDeviceState(deviceId),
        getDeviceConfig(deviceId),
        getCommands(deviceId),
        getAlerts({ deviceId }),
      ])

      setTelemetry(latestTelemetry)
      setDeviceState(latestState)
      setConfig(latestConfig)
      reconcileCommands(commandList.data)
      setAlerts(alertList.data)
      setStatus('ready')
    } catch (loadError) {
      setError(getErrorMessage(loadError))
      setStatus('error')
    }
  }, [deviceId, enabled, reconcileCommands])

  const refreshSnapshot = useCallback(async () => {
    const [latestTelemetry, latestState, commandList, alertList] = await Promise.all([
      getLatestTelemetry(deviceId),
      getDeviceState(deviceId),
      getCommands(deviceId),
      getAlerts({ deviceId }),
    ])

    setTelemetry(latestTelemetry)
    setDeviceState(latestState)
    reconcileCommands(commandList.data)
    setAlerts(alertList.data)
  }, [deviceId, reconcileCommands])

  const refreshHistory = useCallback(async () => {
    const requestId = historyRequestId.current + 1
    historyRequestId.current = requestId
    setHistoryLoading(true)
    setHistoryError(null)
    const { from, to } = getHistoryBounds(historyQuery.range)

    try {
      const response = await getTelemetryHistory({
        deviceId,
        bucket: historyQuery.bucket,
        from,
        to,
        limit: 1_000,
        order: 'asc',
      })
      if (requestId === historyRequestId.current) {
        setHistory(response)
      }
    } catch (loadError) {
      if (requestId === historyRequestId.current) {
        setHistoryError(getErrorMessage(loadError))
      }
    } finally {
      if (requestId === historyRequestId.current) {
        setHistoryLoading(false)
      }
    }
  }, [deviceId, historyQuery])

  const updateHistoryQuery = useCallback((query: HistoryQuery) => {
    historyRequestId.current += 1
    setHistory(null)
    setHistoryError(null)
    setHistoryLoading(true)
    setHistoryQuery(query)
  }, [])

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

      if (message.type === 'ping') {
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
        const receivedAt = new Date().toISOString()
        if (!knownCommandIds.current.has(message.data.commandId)) {
          bufferedCommandResults.current.set(message.data.commandId, {
            data: message.data,
            receivedAt,
          })

          if (bufferedCommandResults.current.size > maxBufferedCommandResults) {
            const oldestCommandId = bufferedCommandResults.current.keys().next().value
            if (oldestCommandId) {
              bufferedCommandResults.current.delete(oldestCommandId)
            }
          }
        }

        setCommands((current) =>
          mergeCommandResult(current, message.data, receivedAt),
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
      }

      socket.onmessage = handleMessage
      socket.onerror = () => socket?.close()
      socket.onclose = () => {
        if (stopped) {
          return
        }

        startPolling()
        reconnectTimer = window.setTimeout(connect, reconnectDelayMs)
      }
    }

    connect()
    return () => {
      stopped = true
      stopPolling()

      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
      }

      socket?.close()
    }
  }, [deviceId, enabled, refreshSnapshot, status])

  const hasPendingCommands = commands.some((command) => command.status === 'PENDING')

  useEffect(() => {
    if (!enabled || status !== 'ready' || !hasPendingCommands) {
      return
    }

    const initialCommandSyncTimer = window.setTimeout(() => {
      void refreshCommands().catch(() => undefined)
    }, 0)
    const commandSyncTimer = window.setInterval(() => {
      void refreshCommands().catch(() => undefined)
    }, pendingCommandSyncMs)

    return () => {
      window.clearTimeout(initialCommandSyncTimer)
      window.clearInterval(commandSyncTimer)
    }
  }, [enabled, hasPendingCommands, refreshCommands, status])

  useEffect(() => {
    if (!enabled || status !== 'ready') {
      return
    }

    const initialHistoryTimer = window.setTimeout(() => {
      void refreshHistory()
    }, 0)
    const historyTimer = window.setInterval(() => {
      void refreshHistory()
    }, historyRefreshMs)

    return () => {
      window.clearTimeout(initialHistoryTimer)
      window.clearInterval(historyTimer)
    }
  }, [enabled, refreshHistory, status])

  const sendCommand = useCallback(async (request: CommandRequest) => {
    const accepted = await postCommand(request)
    const pending = createPendingCommand(request, accepted, new Date().toISOString())
    const bufferedResult = bufferedCommandResults.current.get(accepted.commandId)

    knownCommandIds.current.add(accepted.commandId)
    bufferedCommandResults.current.delete(accepted.commandId)
    setCommands((current) => {
      const withPending = [
        pending,
        ...current.filter((command) => command.commandId !== accepted.commandId),
      ]

      return bufferedResult
        ? mergeCommandResult(withPending, bufferedResult.data, bufferedResult.receivedAt)
        : withPending
    })
  }, [])

  const publishConfig = useCallback(async (nextConfig: DeviceConfig): Promise<ConfigPublished> => {
    const published = await postDeviceConfig(deviceId, nextConfig)
    setConfig(published.config)
    return published
  }, [deviceId])

  const publishMode = useCallback(async (mode: ControlMode): Promise<ConfigPublished> => {
    if (!config) {
      throw new Error('Chưa tải được cấu hình thiết bị.')
    }

    return publishConfig(withMode(config, mode))
  }, [config, publishConfig])

  return {
    status,
    realtimeStatus,
    error,
    telemetry,
    deviceState,
    history,
    historyQuery,
    historyLoading,
    historyError,
    config,
    commands,
    alerts,
    retry: loadInitial,
    sendCommand,
    publishConfig,
    publishMode,
    refreshHistory,
    updateHistoryQuery,
  }
}
