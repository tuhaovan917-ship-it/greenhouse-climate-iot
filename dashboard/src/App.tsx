import { Leaf, LoaderCircle, RefreshCw, ServerOff } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { dashboardConfig } from './api/config'
import { createPendingCommand, mergeCommandResult } from './features/control/commandState'
import { OverviewPage } from './features/overview/OverviewPage'
import { useGreenhouseDashboard } from './hooks/useGreenhouseDashboard'
import {
  mockAlerts,
  mockCommandHistory,
  mockDeviceConfig,
  mockDeviceState,
  mockTelemetry,
  mockTelemetryHistoryByBucket,
} from './mocks/greenhouse'
import type {
  CommandAccepted,
  CommandActivity,
  CommandRequest,
  ConfigPublished,
  ControlMode,
  DeviceConfig,
  DeviceState,
} from './types/api'

function MockDashboard() {
  const [deviceState, setDeviceState] = useState<DeviceState>(mockDeviceState)
  const [config, setConfig] = useState<DeviceConfig>(mockDeviceConfig)
  const [commands, setCommands] = useState<CommandActivity[]>(mockCommandHistory)
  const commandSequence = useRef(0)
  const timers = useRef<number[]>([])

  useEffect(() => {
    const activeTimers = timers.current
    return () => activeTimers.forEach((timer) => window.clearTimeout(timer))
  }, [])

  async function handlePublishMode(mode: ControlMode): Promise<ConfigPublished> {
    if (!deviceState.online) {
      throw new Error('Thiết bị đang ngoại tuyến, không thể publish cấu hình.')
    }

    const nextConfig = { ...config, mode }
    await new Promise((resolve) => window.setTimeout(resolve, 250))
    setConfig(nextConfig)

    const applyTimer = window.setTimeout(() => {
      setDeviceState((current) => ({
        ...current,
        mode,
        updatedAt: new Date().toISOString(),
      }))
    }, 700)
    timers.current.push(applyTimer)

    return { status: 'PUBLISHED', config: nextConfig }
  }

  async function handleSendCommand(request: CommandRequest) {
    await new Promise((resolve) => window.setTimeout(resolve, 250))

    commandSequence.current += 1
    const accepted: CommandAccepted = {
      commandId: `cmd-demo-${Date.now()}-${commandSequence.current}`,
      status: 'PENDING',
    }
    const pendingCommand = createPendingCommand(
      request,
      accepted,
      new Date().toISOString(),
    )
    setCommands((current) => [pendingCommand, ...current])

    const resultTimer = window.setTimeout(() => {
      const completedAt = new Date().toISOString()
      setCommands((current) =>
        mergeCommandResult(
          current,
          { commandId: accepted.commandId, result: 'APPLIED', wasLate: false },
          completedAt,
        ),
      )
      setDeviceState((current) => ({
        ...current,
        [request.device]: request.on,
        lastCommandId: accepted.commandId,
        lastCommandResult: 'APPLIED',
        reason: null,
        updatedAt: completedAt,
      }))
    }, 1_200)
    timers.current.push(resultTimer)
  }

  return (
    <OverviewPage
      telemetry={mockTelemetry}
      deviceState={deviceState}
      history={mockTelemetryHistoryByBucket}
      dataSource="mock"
      control={{
        config,
        commands,
        onSendCommand: handleSendCommand,
        onPublishMode: handlePublishMode,
      }}
      alerts={mockAlerts}
    />
  )
}

interface DashboardLoadStateProps {
  error?: string | null
  onRetry?: () => void
}

function DashboardLoadState({ error, onRetry }: DashboardLoadStateProps) {
  return (
    <main className="grid min-h-screen place-items-center bg-[#f3f7f4] p-6 text-slate-900 dark:bg-[#07110e] dark:text-slate-100">
      <div className="panel-card w-full max-w-md p-7 text-center">
        <span className={`mx-auto grid h-14 w-14 place-items-center rounded-2xl ${error ? 'bg-red-100 text-red-700 dark:bg-red-400/10 dark:text-red-300' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300'}`}>
          {error ? (
            <ServerOff aria-hidden="true" className="h-7 w-7" />
          ) : (
            <Leaf aria-hidden="true" className="h-7 w-7" />
          )}
        </span>
        <h1 className="mt-5 text-xl font-semibold text-slate-950 dark:text-white">
          {error ? 'Chưa kết nối được Backend' : 'Đang tải dữ liệu nhà kính'}
        </h1>
        <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-400">
          {error ?? 'Dashboard đang đồng bộ telemetry, trạng thái, cấu hình và lịch sử cảnh báo.'}
        </p>
        {error && onRetry ? (
          <button
            className="mx-auto mt-6 flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 dark:bg-emerald-300 dark:text-emerald-950 dark:hover:bg-emerald-200"
            onClick={onRetry}
            type="button"
          >
            <RefreshCw aria-hidden="true" className="h-4 w-4" />
            Thử kết nối lại
          </button>
        ) : (
          <LoaderCircle aria-hidden="true" className="mx-auto mt-6 h-5 w-5 animate-spin text-emerald-700 dark:text-emerald-300" />
        )}
      </div>
    </main>
  )
}

function LiveDashboard() {
  const dashboard = useGreenhouseDashboard({
    deviceId: dashboardConfig.deviceId,
    enabled: true,
  })

  if (dashboard.status === 'error') {
    return <DashboardLoadState error={dashboard.error} onRetry={() => void dashboard.retry()} />
  }

  if (
    dashboard.status !== 'ready' ||
    !dashboard.telemetry ||
    !dashboard.deviceState ||
    !dashboard.history ||
    !dashboard.config
  ) {
    return <DashboardLoadState />
  }

  return (
    <OverviewPage
      alerts={dashboard.alerts}
      control={{
        config: dashboard.config,
        commands: dashboard.commands,
        onPublishMode: dashboard.publishMode,
        onSendCommand: dashboard.sendCommand,
      }}
      dataSource="live"
      deviceState={dashboard.deviceState}
      history={dashboard.history}
      realtimeStatus={dashboard.realtimeStatus}
      telemetry={dashboard.telemetry}
    />
  )
}

export default function App() {
  return dashboardConfig.dataSource === 'live' ? <LiveDashboard /> : <MockDashboard />
}
