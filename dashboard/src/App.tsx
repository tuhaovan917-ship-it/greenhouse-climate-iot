import { useEffect, useRef, useState } from 'react'
import { createPendingCommand, mergeCommandResult } from './features/control/commandState'
import { OverviewPage } from './features/overview/OverviewPage'
import {
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

export default function App() {
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
    />
  )
}
