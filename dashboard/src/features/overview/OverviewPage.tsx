import {
  Activity,
  BellRing,
  ChartNoAxesCombined,
  CloudFog,
  Database,
  Droplets,
  Fan,
  Gauge,
  LayoutDashboard,
  Leaf,
  Lightbulb,
  Radio,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  Thermometer,
  Waves,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { ActuatorCard } from '../../components/ActuatorCard'
import { SensorCard } from '../../components/SensorCard'
import { StatusBadge } from '../../components/StatusBadge'
import { ThemeToggle } from '../../components/ThemeToggle'
import type {
  CommandActivity,
  CommandRequest,
  ConfigPublished,
  ControlMode,
  DeviceConfig,
  DeviceState,
  Telemetry,
  TelemetryHistoryResponse,
  Alert,
} from '../../types/api'
import { formatMeasurement, formatTimestamp } from '../../utils/formatters'
import { ControlPanel } from '../control/ControlPanel'
import { AlertsPanel } from '../alerts/AlertsPanel'
import type { HistoryQuery } from '../history/historyQuery'
import { isTelemetryStale } from './telemetryFreshness'

const TelemetryHistoryPanel = lazy(async () => {
  const module = await import('../history/TelemetryHistoryPanel')
  return { default: module.TelemetryHistoryPanel }
})

interface ControlBindings {
  config: DeviceConfig
  commands: CommandActivity[]
  onSendCommand: (request: CommandRequest) => Promise<void>
  onPublishMode: (mode: ControlMode) => Promise<ConfigPublished>
  onPublishConfig: (config: DeviceConfig) => Promise<ConfigPublished>
}

interface OverviewPageProps {
  telemetry: Telemetry | null
  deviceState: DeviceState
  history: TelemetryHistoryResponse | null
  historyLoading?: boolean
  historyError?: string | null
  onHistoryQueryChange?: (query: HistoryQuery) => void
  onRetryHistory?: () => void
  control?: ControlBindings
  alerts?: Alert[]
  realtimeStatus?: 'connecting' | 'connected' | 'polling'
}

const navigationItems = [
  { label: 'Tổng quan', icon: LayoutDashboard, href: '#overview', active: true },
  { label: 'Lịch sử', icon: ChartNoAxesCombined, href: '#history', active: false },
  { label: 'Điều khiển', icon: SlidersHorizontal, href: '#control', active: false },
  { label: 'Cảnh báo', icon: BellRing, href: '#alerts', active: false },
]

function getWaterStatus(telemetry: Telemetry | null) {
  if (telemetry === null) {
    return {
      value: 'Chưa có dữ liệu',
      helper: 'Đang chờ telemetry từ thiết bị',
      tone: 'neutral' as const,
    }
  }

  const { waterOk } = telemetry

  if (waterOk === true) {
    return {
      value: 'Đủ nước',
      helper: 'Mực nước an toàn cho bơm',
      tone: 'positive' as const,
    }
  }

  if (waterOk === false) {
    return {
      value: 'Hết nước',
      helper: 'Bơm bị khóa bởi failsafe',
      tone: 'critical' as const,
    }
  }

  return {
    value: 'Không rõ',
    helper: 'Cảm biến nước không đáng tin cậy',
    tone: 'warning' as const,
  }
}

export function OverviewPage({
  telemetry,
  deviceState,
  history,
  historyLoading = false,
  historyError = null,
  onHistoryQueryChange = () => undefined,
  onRetryHistory = () => undefined,
  control,
  alerts,
  realtimeStatus,
}: OverviewPageProps) {
  const [nowMs, setNowMs] = useState(() => Date.now())
  const waterStatus = getWaterStatus(telemetry)
  const temperature = formatMeasurement(telemetry?.temperatureC ?? null)
  const humidity = formatMeasurement(telemetry?.humidityPct ?? null)
  const light = formatMeasurement(telemetry?.lightLux ?? null, {
    maximumFractionDigits: 0,
  })
  const missingTelemetryHelper = 'Chưa nhận được telemetry từ thiết bị'
  const telemetryStale = isTelemetryStale(telemetry, deviceState.online, nowMs)

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 5_000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className="min-h-screen overflow-x-hidden bg-[#f3f7f4] text-slate-900 transition-colors duration-300 dark:bg-[#07110e] dark:text-slate-100">
      <div aria-hidden="true" className="page-glow" />
      <div className="relative mx-auto grid min-h-screen max-w-[1680px] lg:grid-cols-[15.5rem_minmax(0,1fr)]">
        <aside className="border-b border-slate-200/80 bg-white/45 px-5 py-5 backdrop-blur-xl dark:border-white/[0.07] dark:bg-black/10 lg:sticky lg:top-0 lg:h-screen lg:border-b-0 lg:border-r lg:px-6 lg:py-7">
          <div className="flex items-center justify-between lg:block">
            <div className="flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-2xl border border-emerald-600/20 bg-emerald-100/80 text-emerald-700 shadow-[0_0_30px_rgba(52,211,153,0.09)] dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300">
                <Leaf aria-hidden="true" className="h-5 w-5" />
              </span>
              <div>
                <p className="text-sm font-bold tracking-tight text-slate-950 dark:text-white">Greenhouse</p>
                <p className="text-[0.65rem] font-semibold uppercase tracking-[0.2em] text-emerald-700/70 dark:text-emerald-400/70">
                  Climate OS
                </p>
              </div>
            </div>

            <div className="lg:mt-10">
              <StatusBadge
                tone={deviceState.online ? 'positive' : 'critical'}
                showDot
              >
                {deviceState.online ? 'Trực tuyến' : 'Ngoại tuyến'}
              </StatusBadge>
            </div>
          </div>

          <nav aria-label="Điều hướng Dashboard" className="mt-6 hidden lg:block">
            <p className="px-3 text-[0.65rem] font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">
              Không gian làm việc
            </p>
            <ul className="mt-3 space-y-1">
              {navigationItems.map(({ label, icon: Icon, href, active }) => (
                <li key={label}>
                  {href ? (
                    <a
                      aria-current={active ? 'page' : undefined}
                      className={`flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300 ${
                        active
                          ? 'bg-emerald-100/80 font-semibold text-emerald-800 dark:bg-emerald-400/10 dark:text-emerald-200'
                          : 'text-slate-600 hover:bg-white/70 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/[0.035] dark:hover:text-slate-100'
                      }`}
                      href={href}
                    >
                      <Icon aria-hidden="true" className="h-4 w-4" />
                      <span>{label}</span>
                    </a>
                  ) : (
                    <div className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm text-slate-500 dark:text-slate-400">
                      <Icon aria-hidden="true" className="h-4 w-4" />
                      <span>{label}</span>
                      <span className="ml-auto text-[0.55rem] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500">
                        Sắp có
                      </span>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </nav>

          <div className="mt-8 hidden rounded-2xl border border-slate-200/80 bg-white/55 p-4 dark:border-white/[0.07] dark:bg-white/[0.025] lg:block">
            <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
              <Database aria-hidden="true" className="h-4 w-4" />
              <p className="text-xs font-semibold">Nguồn dữ liệu</p>
            </div>
            <p className="mt-3 font-mono text-xs text-slate-700 dark:text-slate-300">{deviceState.deviceId}</p>
            <div className="mt-4 h-px bg-slate-200 dark:bg-white/[0.06]" />
            <p className="mt-4 text-[0.68rem] leading-5 text-slate-500 dark:text-slate-400">
              Dashboard chỉ đọc trạng thái thực tế từ Backend qua REST/WebSocket.
            </p>
          </div>
        </aside>

        <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-8 lg:py-8 xl:px-10" id="overview">
          <header className="flex flex-col gap-5 border-b border-slate-200/80 pb-6 dark:border-white/[0.07] sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="eyebrow">Greenhouse / Tổng quan</p>
              <h1 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950 dark:text-white sm:text-3xl">
                Theo dõi khí hậu
              </h1>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <ThemeToggle />
              {realtimeStatus ? (
                <StatusBadge
                  tone={realtimeStatus === 'connected' ? 'positive' : realtimeStatus === 'polling' ? 'warning' : 'neutral'}
                  showDot
                >
                  {realtimeStatus === 'connected'
                    ? 'Realtime'
                    : realtimeStatus === 'polling'
                      ? 'Polling mỗi 5 giây'
                      : 'Đang kết nối WS'}
                </StatusBadge>
              ) : null}
              <StatusBadge
                tone={deviceState.online ? telemetryStale ? 'warning' : 'positive' : 'critical'}
                showDot
              >
                {deviceState.online
                  ? telemetryStale
                    ? 'Dữ liệu chậm cập nhật'
                    : 'Hệ thống ổn định'
                  : 'Mất kết nối'}
              </StatusBadge>
            </div>
          </header>

          <section className="relative overflow-hidden border-b border-slate-200/80 py-8 dark:border-white/[0.07] sm:py-10">
            <div aria-hidden="true" className="hero-grid" />
            <div className="relative grid gap-7 xl:grid-cols-[minmax(0,1fr)_22rem] xl:items-end">
              <div>
                <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
                  <Radio aria-hidden="true" className="h-4 w-4" />
                  <span className="text-xs font-bold uppercase tracking-[0.18em]">
                    Cập nhật gần nhất
                  </span>
                </div>
                {telemetry && deviceState.online && !telemetryStale ? (
                  <p className="mt-4 max-w-3xl text-3xl font-semibold leading-tight tracking-[-0.045em] text-slate-950 dark:text-white sm:text-4xl xl:text-5xl">
                    Môi trường đang ở trạng thái{' '}
                    <span className="text-emerald-700 dark:text-emerald-300">ổn định.</span>
                  </p>
                ) : telemetry && !deviceState.online ? (
                  <p className="mt-4 max-w-3xl text-3xl font-semibold leading-tight tracking-[-0.045em] text-slate-950 dark:text-white sm:text-4xl xl:text-5xl">
                    Thiết bị đang{' '}
                    <span className="text-red-700 dark:text-red-300">ngoại tuyến.</span>
                  </p>
                ) : telemetryStale ? (
                  <p className="mt-4 max-w-3xl text-3xl font-semibold leading-tight tracking-[-0.045em] text-slate-950 dark:text-white sm:text-4xl xl:text-5xl">
                    Dữ liệu đang{' '}
                    <span className="text-amber-700 dark:text-amber-300">chậm cập nhật.</span>
                  </p>
                ) : (
                  <p className="mt-4 max-w-3xl text-3xl font-semibold leading-tight tracking-[-0.045em] text-slate-950 dark:text-white sm:text-4xl xl:text-5xl">
                    Đang chờ{' '}
                    <span className="text-amber-700 dark:text-amber-300">bản tin telemetry đầu tiên.</span>
                  </p>
                )}
                <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-400">
                  Các chỉ số dưới đây phản ánh dữ liệu và trạng thái thiết bị thực tế gần nhất.
                  Lệnh điều khiển sẽ không được xem là thành công cho đến khi có phản hồi từ ESP32.
                </p>
              </div>

              <div className="rounded-2xl border border-slate-200/80 bg-white/65 p-5 shadow-sm backdrop-blur-sm dark:border-white/[0.08] dark:bg-black/20 dark:shadow-none">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-medium text-slate-500">Thiết bị</p>
                    <p className="mt-1 font-mono text-sm font-semibold text-slate-800 dark:text-slate-200">
                      {deviceState.deviceId}
                    </p>
                  </div>
                  {deviceState.online ? (
                    <Wifi aria-hidden="true" className="h-5 w-5 text-emerald-700 dark:text-emerald-300" />
                  ) : (
                    <WifiOff aria-hidden="true" className="h-5 w-5 text-red-600 dark:text-red-300" />
                  )}
                </div>
                <div className="mt-5 grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-slate-100/80 p-3 dark:bg-white/[0.035]">
                    <p className="text-[0.65rem] uppercase tracking-wider text-slate-500 dark:text-slate-400">Chế độ</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{deviceState.mode}</p>
                  </div>
                  <div className="rounded-xl bg-slate-100/80 p-3 dark:bg-white/[0.035]">
                    <p className="text-[0.65rem] uppercase tracking-wider text-slate-500 dark:text-slate-400">Failsafe</p>
                    <p
                      className={`mt-2 text-sm font-semibold ${
                        deviceState.failsafeActive
                          ? 'text-amber-700 dark:text-amber-200'
                          : 'text-emerald-700 dark:text-emerald-300'
                      }`}
                    >
                      {deviceState.failsafeActive ? 'Đang bật' : 'Bình thường'}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section aria-labelledby="sensor-heading" className="py-8">
            <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="eyebrow">Dữ liệu môi trường</p>
                <h2 id="sensor-heading" className="mt-2 text-xl font-semibold tracking-tight text-slate-950 dark:text-white">
                  Chỉ số mới nhất
                </h2>
              </div>
              <p className="text-xs text-slate-600 dark:text-slate-400">
                Nhận lúc {formatTimestamp(telemetry?.receivedAt ?? null)}
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-4">
              <SensorCard
                title="Nhiệt độ"
                value={temperature}
                unit={telemetry?.temperatureC == null ? undefined : '°C'}
                helper={
                  telemetry === null
                    ? missingTelemetryHelper
                    : telemetry.temperatureC === null
                      ? 'Cảm biến chưa cung cấp giá trị hợp lệ'
                    : 'Trong vùng theo dõi hiện tại'
                }
                icon={Thermometer}
                accentClass="bg-orange-400"
              />
              <SensorCard
                title="Độ ẩm không khí"
                value={humidity}
                unit={telemetry?.humidityPct == null ? undefined : '%'}
                helper={
                  telemetry === null
                    ? missingTelemetryHelper
                    : telemetry.humidityPct === null
                      ? 'Cảm biến chưa cung cấp giá trị hợp lệ'
                    : 'Độ ẩm phù hợp với cấu hình'
                }
                icon={Droplets}
                accentClass="bg-sky-400"
              />
              <SensorCard
                title="Cường độ sáng"
                value={light}
                unit={telemetry?.lightLux == null ? undefined : 'lux'}
                helper={
                  telemetry === null
                    ? missingTelemetryHelper
                    : telemetry.lightLux === null
                      ? 'Cảm biến chưa cung cấp giá trị hợp lệ'
                    : 'Đèn được điều khiển theo ngưỡng'
                }
                icon={Sun}
                accentClass="bg-amber-300"
              />
              <SensorCard
                title="Nguồn nước"
                value={waterStatus.value}
                helper={<StatusBadge tone={waterStatus.tone}>{waterStatus.helper}</StatusBadge>}
                icon={Waves}
                accentClass="bg-emerald-400"
                valueLabel={`Nguồn nước: ${waterStatus.value}`}
              />
            </div>
          </section>

          <Suspense
            fallback={(
              <section className="pb-8" id="history">
                <div className="panel-card grid min-h-72 place-items-center p-6 text-sm text-slate-600 dark:text-slate-400">
                  Đang tải biểu đồ lịch sử…
                </div>
              </section>
            )}
          >
            <TelemetryHistoryPanel
              error={historyError}
              history={history}
              loading={historyLoading}
              onQueryChange={onHistoryQueryChange}
              onRetry={onRetryHistory}
            />
          </Suspense>

          <section className="grid gap-4 pb-10 xl:grid-cols-[minmax(0,1.45fr)_minmax(20rem,0.85fr)]">
            <article className="panel-card p-5 sm:p-6">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="eyebrow">Thiết bị chấp hành</p>
                  <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-950 dark:text-white">
                    Trạng thái thực tế
                  </h2>
                </div>
                <StatusBadge tone="neutral">Không điều khiển trực tiếp</StatusBadge>
              </div>

              <div className="mt-6 grid gap-3 lg:grid-cols-3">
                <ActuatorCard
                  name="Quạt thông gió"
                  description="Điều hòa nhiệt độ"
                  active={deviceState.fan}
                  icon={Fan}
                />
                <ActuatorCard
                  name="Bơm phun sương"
                  description="Duy trì độ ẩm"
                  active={deviceState.mist}
                  icon={CloudFog}
                />
                <ActuatorCard
                  name="Đèn trồng cây"
                  description="Bổ sung ánh sáng"
                  active={deviceState.lamp}
                  icon={Lightbulb}
                />
              </div>
            </article>

            <article className="panel-card p-5 sm:p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="eyebrow">Sức khỏe hệ thống</p>
                  <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-950 dark:text-white">
                    Kết nối & an toàn
                  </h2>
                </div>
                <span className="icon-tile">
                  <Activity aria-hidden="true" className="h-5 w-5" />
                </span>
              </div>

              <dl className="mt-6 space-y-4">
                <div className="flex items-center justify-between gap-4 border-b border-slate-200/80 pb-4 dark:border-white/[0.06]">
                  <dt className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                    <Gauge aria-hidden="true" className="h-4 w-4 text-slate-500 dark:text-slate-400" />
                    Chế độ vận hành
                  </dt>
                  <dd className="text-sm font-semibold text-slate-900 dark:text-white">{deviceState.mode}</dd>
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-slate-200/80 pb-4 dark:border-white/[0.06]">
                  <dt className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                    <ShieldCheck aria-hidden="true" className="h-4 w-4 text-slate-500 dark:text-slate-400" />
                    Cơ chế an toàn
                  </dt>
                  <dd>
                    <StatusBadge tone={deviceState.failsafeActive ? 'warning' : 'positive'}>
                      {deviceState.failsafeActive ? 'Đang can thiệp' : 'Sẵn sàng'}
                    </StatusBadge>
                  </dd>
                </div>
                <div className="flex items-start justify-between gap-4">
                  <dt className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                    <Wifi aria-hidden="true" className="mt-0.5 h-4 w-4 text-slate-500 dark:text-slate-400" />
                    Lần cuối nhận tin
                  </dt>
                  <dd className="max-w-44 text-right text-xs leading-5 text-slate-700 dark:text-slate-300">
                    {formatTimestamp(deviceState.lastSeenAt)}
                  </dd>
                </div>
              </dl>
            </article>
          </section>

          {control ? (
            <ControlPanel
              commands={control.commands}
              config={control.config}
              deviceState={deviceState}
              onPublishMode={control.onPublishMode}
              onPublishConfig={control.onPublishConfig}
              onSendCommand={control.onSendCommand}
              telemetry={telemetry}
            />
          ) : null}

          {alerts ? <AlertsPanel alerts={alerts} /> : null}
        </main>
      </div>
    </div>
  )
}
