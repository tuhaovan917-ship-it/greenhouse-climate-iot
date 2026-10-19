import {
  AlertTriangle,
  CheckCircle2,
  CloudFog,
  Fan,
  Lightbulb,
  LoaderCircle,
  RadioTower,
  ShieldAlert,
  SlidersHorizontal,
  TimerOff,
  XCircle,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { StatusBadge } from '../../components/StatusBadge'
import type {
  CommandActivity,
  CommandRequest,
  ConfigPublished,
  ControlMode,
  DeviceConfig,
  DeviceName,
  DeviceState,
  Telemetry,
} from '../../types/api'
import { formatTimestamp } from '../../utils/formatters'

interface ControlPanelProps {
  telemetry: Telemetry
  deviceState: DeviceState
  config: DeviceConfig
  commands: CommandActivity[]
  onSendCommand: (request: CommandRequest) => Promise<void>
  onPublishMode: (mode: ControlMode) => Promise<ConfigPublished>
}

const deviceMeta: Record<
  DeviceName,
  { name: string; description: string; icon: typeof Fan }
> = {
  fan: {
    name: 'Quạt thông gió',
    description: 'Điều hòa nhiệt độ',
    icon: Fan,
  },
  mist: {
    name: 'Bơm phun sương',
    description: 'Duy trì độ ẩm',
    icon: CloudFog,
  },
  lamp: {
    name: 'Đèn trồng cây',
    description: 'Bổ sung ánh sáng',
    icon: Lightbulb,
  },
}

const commandTone = {
  PENDING: 'warning',
  APPLIED: 'positive',
  REJECTED: 'critical',
  TIMEOUT: 'neutral',
} as const

const commandLabel = {
  PENDING: 'Đang chờ',
  APPLIED: 'Đã áp dụng',
  REJECTED: 'Bị từ chối',
  TIMEOUT: 'Quá thời gian',
} as const

const reasonLabels: Record<string, string> = {
  NO_WATER: 'Hết nước — bơm bị khóa an toàn',
  SENSOR_FAULT: 'Cảm biến nước không đáng tin cậy',
  NOT_MANUAL_MODE: 'Thiết bị không ở chế độ MANUAL',
  DEVICE_OFFLINE: 'Thiết bị đang ngoại tuyến',
  MQTT_NOT_CONNECTED: 'Backend chưa kết nối MQTT',
}

function getBlockReason(
  device: DeviceName,
  requestedOn: boolean,
  telemetry: Telemetry,
  deviceState: DeviceState,
) {
  if (!deviceState.online) {
    return 'Thiết bị đang ngoại tuyến'
  }

  if (deviceState.mode !== 'MANUAL') {
    return 'Chỉ điều khiển trực tiếp trong chế độ MANUAL'
  }

  if (device === 'mist' && requestedOn && telemetry.waterOk !== true) {
    return telemetry.waterOk === false
      ? 'Hết nước — failsafe khóa bơm'
      : 'Chưa xác minh được cảm biến nước'
  }

  return null
}

function CommandStatusIcon({ status }: { status: CommandActivity['status'] }) {
  const iconClass = 'h-4 w-4'

  if (status === 'PENDING') {
    return <LoaderCircle aria-hidden="true" className={`${iconClass} animate-spin`} />
  }

  if (status === 'APPLIED') {
    return <CheckCircle2 aria-hidden="true" className={iconClass} />
  }

  if (status === 'REJECTED') {
    return <XCircle aria-hidden="true" className={iconClass} />
  }

  return <TimerOff aria-hidden="true" className={iconClass} />
}

export function ControlPanel({
  telemetry,
  deviceState,
  config,
  commands,
  onSendCommand,
  onPublishMode,
}: ControlPanelProps) {
  const [submittingDevice, setSubmittingDevice] = useState<DeviceName | null>(null)
  const [publishingMode, setPublishingMode] = useState(false)
  const [modeNotice, setModeNotice] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const awaitingModeConfirmation = config.mode !== deviceState.mode

  const pendingByDevice = useMemo(() => {
    const pending = new Set<DeviceName>()
    commands.forEach((command) => {
      if (command.status === 'PENDING') {
        pending.add(command.device)
      }
    })
    return pending
  }, [commands])

  async function handleCommand(device: DeviceName) {
    const requestedOn = !deviceState[device]
    const blockReason = getBlockReason(device, requestedOn, telemetry, deviceState)

    if (blockReason) {
      return
    }

    setSubmittingDevice(device)
    setErrorMessage(null)

    try {
      await onSendCommand({
        deviceId: deviceState.deviceId,
        device,
        on: requestedOn,
      })
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Không thể gửi lệnh')
    } finally {
      setSubmittingDevice(null)
    }
  }

  async function handleModeChange() {
    const nextMode: ControlMode = deviceState.mode === 'AUTO' ? 'MANUAL' : 'AUTO'
    setPublishingMode(true)
    setModeNotice(null)
    setErrorMessage(null)

    try {
      const response = await onPublishMode(nextMode)
      setModeNotice(
        `Đã publish yêu cầu ${response.config.mode}. Đang chờ trạng thái thực tế từ ESP32.`,
      )
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Không thể publish cấu hình')
    } finally {
      setPublishingMode(false)
    }
  }

  return (
    <section aria-labelledby="control-heading" className="pb-10" id="control">
      <div className="panel-card overflow-hidden">
        <div className="grid gap-6 border-b border-slate-200/80 p-5 dark:border-white/[0.07] sm:p-6 xl:grid-cols-[minmax(0,1fr)_22rem] xl:items-center">
          <div>
            <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
              <SlidersHorizontal aria-hidden="true" className="h-4 w-4" />
              <p className="eyebrow !text-current">Điều khiển từ xa</p>
            </div>
            <h2 id="control-heading" className="mt-2 text-xl font-semibold tracking-tight text-slate-950 dark:text-white">
              Thiết bị & vòng đời lệnh
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-400">
              Dashboard chỉ gửi yêu cầu. Trạng thái bật/tắt bên dưới luôn lấy từ phản hồi thực tế của ESP32.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white/60 p-4 dark:border-white/[0.08] dark:bg-black/15">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs text-slate-500 dark:text-slate-400">Chế độ thực tế</p>
                <p className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">{deviceState.mode}</p>
              </div>
              <button
                className="rounded-xl border border-emerald-700/25 bg-emerald-100/80 px-4 py-2 text-xs font-semibold text-emerald-900 transition hover:bg-emerald-200/80 disabled:cursor-not-allowed disabled:opacity-50 dark:border-emerald-400/25 dark:bg-emerald-400/10 dark:text-emerald-200 dark:hover:bg-emerald-400/15"
                disabled={!deviceState.online || publishingMode || awaitingModeConfirmation}
                onClick={handleModeChange}
                type="button"
              >
                {publishingMode
                  ? 'Đang publish…'
                  : awaitingModeConfirmation
                    ? 'Đang chờ ESP32'
                    : `Yêu cầu ${deviceState.mode === 'AUTO' ? 'MANUAL' : 'AUTO'}`}
              </button>
            </div>
            <p className="mt-3 text-[0.68rem] leading-5 text-slate-500 dark:text-slate-400">
              Desired config hiện tại: {config.mode}. PUBLISHED chưa đồng nghĩa ESP32 đã áp dụng.
            </p>
          </div>
        </div>

        {modeNotice ? (
          <div className="flex items-start gap-2 border-b border-sky-700/15 bg-sky-50/80 px-5 py-3 text-xs text-sky-900 dark:border-sky-300/10 dark:bg-sky-300/[0.06] dark:text-sky-200 sm:px-6">
            <RadioTower aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
            <p>{modeNotice}</p>
          </div>
        ) : null}

        {errorMessage ? (
          <div role="alert" className="flex items-start gap-2 border-b border-red-700/15 bg-red-50/80 px-5 py-3 text-xs text-red-900 dark:border-red-300/10 dark:bg-red-300/[0.06] dark:text-red-200 sm:px-6">
            <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
            <p>{errorMessage}</p>
          </div>
        ) : null}

        <div className="grid gap-4 p-5 sm:p-6 lg:grid-cols-3">
          {(Object.keys(deviceMeta) as DeviceName[]).map((device) => {
            const meta = deviceMeta[device]
            const Icon = meta.icon
            const actualOn = deviceState[device]
            const requestedOn = !actualOn
            const blockReason = getBlockReason(device, requestedOn, telemetry, deviceState)
            const isPending = pendingByDevice.has(device)
            const isSubmitting = submittingDevice === device
            const disabled = Boolean(blockReason) || isPending || isSubmitting

            return (
              <article key={device} className="rounded-2xl border border-slate-200/80 bg-white/55 p-4 dark:border-white/[0.07] dark:bg-white/[0.025]">
                <div className="flex items-start justify-between gap-3">
                  <span className={`grid h-11 w-11 place-items-center rounded-xl border ${actualOn ? 'border-emerald-600/20 bg-emerald-100/80 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300' : 'border-slate-200 bg-slate-100 text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400'}`}>
                    <Icon aria-hidden="true" className="h-5 w-5" />
                  </span>
                  <StatusBadge tone={actualOn ? 'positive' : 'neutral'}>
                    {actualOn ? 'Đang bật' : 'Đang tắt'}
                  </StatusBadge>
                </div>
                <h3 className="mt-4 text-sm font-semibold text-slate-950 dark:text-white">{meta.name}</h3>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{meta.description}</p>
                <button
                  aria-label={`${requestedOn ? 'Bật' : 'Tắt'} ${meta.name}`}
                  className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 dark:bg-emerald-300 dark:text-emerald-950 dark:hover:bg-emerald-200 dark:disabled:bg-white/[0.06] dark:disabled:text-slate-500"
                  disabled={disabled}
                  onClick={() => handleCommand(device)}
                  title={blockReason ?? undefined}
                  type="button"
                >
                  {isPending || isSubmitting ? (
                    <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" />
                  ) : null}
                  {isPending ? 'Đang chờ phản hồi' : isSubmitting ? 'Đang gửi' : `Yêu cầu ${requestedOn ? 'bật' : 'tắt'}`}
                </button>
                <p className={`mt-3 min-h-10 text-[0.68rem] leading-5 ${blockReason ? 'text-amber-800 dark:text-amber-200' : 'text-slate-500 dark:text-slate-400'}`}>
                  {blockReason ?? 'Lệnh mới sẽ có commandId riêng và không tự gửi lại khi timeout.'}
                </p>
              </article>
            )
          })}
        </div>

        <div className="border-t border-slate-200/80 p-5 dark:border-white/[0.07] sm:p-6">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="eyebrow">Nhật ký gần đây</p>
              <h3 className="mt-2 text-base font-semibold text-slate-950 dark:text-white">Kết quả theo commandId</h3>
            </div>
            <StatusBadge tone="neutral">Không tự động gửi lại</StatusBadge>
          </div>

          {commands.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-white/10 dark:text-slate-400">
              Chưa có lệnh điều khiển nào.
            </div>
          ) : (
            <ul className="mt-5 divide-y divide-slate-200/80 overflow-hidden rounded-2xl border border-slate-200/80 bg-white/50 dark:divide-white/[0.06] dark:border-white/[0.07] dark:bg-black/10">
              {commands.slice(0, 6).map((command) => {
                const meta = deviceMeta[command.device]
                const reason = command.reason
                  ? reasonLabels[command.reason] ?? command.reason
                  : null

                return (
                  <li className="grid gap-3 p-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center" key={command.commandId}>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white">
                          {command.requestedOn ? 'Bật' : 'Tắt'} {meta.name.toLowerCase()}
                        </p>
                        {command.wasLate ? <StatusBadge tone="warning">Phản hồi trễ</StatusBadge> : null}
                      </div>
                      <p className="mt-1 truncate font-mono text-[0.68rem] text-slate-500 dark:text-slate-400">{command.commandId}</p>
                      <p className="mt-1 text-[0.68rem] text-slate-500 dark:text-slate-400">
                        Yêu cầu lúc {formatTimestamp(command.requestedAt)}
                        {reason ? ` · ${reason}` : ''}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 md:justify-end">
                      <span className={command.status === 'TIMEOUT' ? 'text-slate-500 dark:text-slate-400' : command.status === 'REJECTED' ? 'text-red-700 dark:text-red-300' : command.status === 'APPLIED' ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-200'}>
                        <CommandStatusIcon status={command.status} />
                      </span>
                      <StatusBadge tone={commandTone[command.status]}>{commandLabel[command.status]}</StatusBadge>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}

          <div className="mt-4 flex items-start gap-2 rounded-xl border border-amber-700/15 bg-amber-50/70 p-3 text-[0.68rem] leading-5 text-amber-900 dark:border-amber-300/10 dark:bg-amber-300/[0.05] dark:text-amber-200">
            <ShieldAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
            <p>TIMEOUT là tạm thời. Phản hồi đến muộn vẫn được cập nhật thành APPLIED/REJECTED và đánh dấu “Phản hồi trễ”.</p>
          </div>
        </div>
      </div>
    </section>
  )
}
