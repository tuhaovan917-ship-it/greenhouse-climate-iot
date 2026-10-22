import {
  BellRing,
  CheckCircle2,
  Clock3,
  Droplets,
  RadioTower,
  ShieldAlert,
  TriangleAlert,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { StatusBadge } from '../../components/StatusBadge'
import type { Alert, AlertCode, AlertSeverity } from '../../types/api'
import { formatTimestamp } from '../../utils/formatters'

interface AlertsPanelProps {
  alerts: Alert[]
}

type AlertView = 'active' | 'history'

const severityMeta: Record<
  AlertSeverity,
  { label: string; tone: 'positive' | 'warning' | 'critical' | 'neutral' }
> = {
  INFO: { label: 'Thông tin', tone: 'neutral' },
  WARNING: { label: 'Cảnh báo', tone: 'warning' },
  CRITICAL: { label: 'Nghiêm trọng', tone: 'critical' },
}

const codeMeta: Record<AlertCode, { label: string; icon: typeof Droplets }> = {
  NO_WATER: { label: 'Hết nước', icon: Droplets },
  SENSOR_FAULT: { label: 'Lỗi cảm biến', icon: TriangleAlert },
  OFFLINE: { label: 'Mất kết nối', icon: RadioTower },
}

function sortAlerts(alerts: Alert[]) {
  return [...alerts].sort((left, right) => {
    const timeDifference = Date.parse(right.startedAt) - Date.parse(left.startedAt)
    return timeDifference === 0 ? right.id - left.id : timeDifference
  })
}

export function AlertsPanel({ alerts }: AlertsPanelProps) {
  const [view, setView] = useState<AlertView>('active')
  const activeCount = alerts.filter((alert) => alert.active).length
  const resolvedCount = alerts.length - activeCount

  const visibleAlerts = useMemo(
    () => sortAlerts(alerts.filter((alert) => (view === 'active' ? alert.active : !alert.active))),
    [alerts, view],
  )

  return (
    <section aria-labelledby="alerts-heading" className="pb-10" id="alerts">
      <div className="panel-card p-5 sm:p-6">
        <div className="flex flex-col gap-5 border-b border-slate-200/80 pb-5 dark:border-white/[0.07] sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
              <BellRing aria-hidden="true" className="h-4 w-4" />
              <p className="eyebrow !text-current">Giám sát an toàn</p>
            </div>
            <h2 id="alerts-heading" className="mt-2 text-xl font-semibold tracking-tight text-slate-950 dark:text-white">
              Cảnh báo hệ thống
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-400">
              WebSocket cập nhật realtime; REST giữ lịch sử để khôi phục đầy đủ sau reload hoặc reconnect.
            </p>
          </div>

          <div aria-label="Bộ lọc cảnh báo" className="inline-flex w-fit rounded-xl border border-slate-200 bg-slate-100/80 p-1 dark:border-white/[0.07] dark:bg-white/[0.035]" role="group">
            <button
              aria-pressed={view === 'active'}
              className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${view === 'active' ? 'bg-white text-slate-950 shadow-sm dark:bg-white/10 dark:text-white' : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'}`}
              onClick={() => setView('active')}
              type="button"
            >
              Đang hoạt động ({activeCount})
            </button>
            <button
              aria-pressed={view === 'history'}
              className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${view === 'history' ? 'bg-white text-slate-950 shadow-sm dark:bg-white/10 dark:text-white' : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'}`}
              onClick={() => setView('history')}
              type="button"
            >
              Đã xử lý ({resolvedCount})
            </button>
          </div>
        </div>

        {visibleAlerts.length === 0 ? (
          <div className="mt-6 grid min-h-44 place-items-center rounded-2xl border border-dashed border-emerald-700/20 bg-emerald-50/50 p-6 text-center dark:border-emerald-300/10 dark:bg-emerald-300/[0.035]">
            <div>
              <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300">
                <CheckCircle2 aria-hidden="true" className="h-6 w-6" />
              </span>
              <h3 className="mt-4 text-sm font-semibold text-slate-950 dark:text-white">
                {view === 'active' ? 'Không có cảnh báo đang hoạt động' : 'Chưa có cảnh báo đã xử lý'}
              </h3>
              <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
                {view === 'active'
                  ? 'Các điều kiện an toàn hiện đều bình thường.'
                  : 'Lịch sử sẽ xuất hiện sau khi một cảnh báo được đóng.'}
              </p>
            </div>
          </div>
        ) : (
          <ul className="mt-6 grid gap-4 lg:grid-cols-2">
            {visibleAlerts.map((alert) => {
              const code = codeMeta[alert.code]
              const severity = severityMeta[alert.severity]
              const Icon = code.icon

              return (
                <li className="rounded-2xl border border-slate-200/80 bg-white/55 p-4 dark:border-white/[0.07] dark:bg-white/[0.025]" key={alert.id}>
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl border ${alert.severity === 'CRITICAL' ? 'border-red-600/20 bg-red-100/80 text-red-700 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-300' : alert.severity === 'WARNING' ? 'border-amber-600/20 bg-amber-100/80 text-amber-700 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-200' : 'border-slate-200 bg-slate-100 text-slate-600 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-300'}`}>
                        <Icon aria-hidden="true" className="h-5 w-5" />
                      </span>
                      <div className="min-w-0">
                        <h3 className="text-sm font-semibold text-slate-950 dark:text-white">{code.label}</h3>
                        <p className="mt-1 font-mono text-[0.65rem] text-slate-500 dark:text-slate-400">{alert.code} · #{alert.id}</p>
                      </div>
                    </div>
                    <StatusBadge tone={severity.tone}>{severity.label}</StatusBadge>
                  </div>

                  <p className="mt-4 text-sm leading-6 text-slate-700 dark:text-slate-300">{alert.message}</p>

                  <dl className="mt-4 grid gap-3 border-t border-slate-200/80 pt-4 text-xs dark:border-white/[0.06] sm:grid-cols-2">
                    <div>
                      <dt className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                        <Clock3 aria-hidden="true" className="h-3.5 w-3.5" />
                        Bắt đầu
                      </dt>
                      <dd className="mt-1 text-slate-800 dark:text-slate-200">{formatTimestamp(alert.startedAt)}</dd>
                    </div>
                    <div>
                      <dt className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                        {alert.active ? <ShieldAlert aria-hidden="true" className="h-3.5 w-3.5" /> : <CheckCircle2 aria-hidden="true" className="h-3.5 w-3.5" />}
                        {alert.active ? 'Gặp gần nhất' : 'Đã xử lý'}
                      </dt>
                      <dd className="mt-1 text-slate-800 dark:text-slate-200">
                        {formatTimestamp(alert.active ? alert.lastSeenAt : alert.resolvedAt)}
                      </dd>
                    </div>
                  </dl>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}
