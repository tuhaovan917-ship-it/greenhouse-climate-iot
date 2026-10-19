import { useMemo, useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ChartNoAxesCombined, CircleAlert } from 'lucide-react'
import type { Bucket, TelemetryHistoryByBucket, TelemetryHistoryResponse } from '../../types/api'
import { formatMeasurement } from '../../utils/formatters'
import {
  normalizeTelemetryHistory,
  type ChartPoint,
} from './historyTransform'

interface TelemetryHistoryPanelProps {
  history: TelemetryHistoryByBucket
}

interface MetricChartProps {
  data: ChartPoint[]
  dataKey: 'temperatureC' | 'humidityPct' | 'lightLux'
  title: string
  unit: string
  color: string
}

const bucketOptions: Array<{ value: Bucket; label: string; description: string }> = [
  { value: 'raw', label: 'Raw', description: 'Mẫu thô' },
  { value: '1m', label: '1 phút', description: 'Trung bình mỗi phút' },
  { value: '5m', label: '5 phút', description: 'Trung bình mỗi 5 phút' },
  { value: '1h', label: '1 giờ', description: 'Trung bình mỗi giờ' },
]

const axisTimeFormatter = new Intl.DateTimeFormat('vi-VN', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const fullTimeFormatter = new Intl.DateTimeFormat('vi-VN', {
  hour: '2-digit',
  minute: '2-digit',
  day: '2-digit',
  month: '2-digit',
  hour12: false,
})

function MetricChart({ data, dataKey, title, unit, color }: MetricChartProps) {
  const gradientId = `history-gradient-${dataKey}`

  return (
    <article className="rounded-2xl border border-slate-200/80 bg-white/55 p-4 dark:border-white/[0.07] dark:bg-black/15 sm:p-5">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Đơn vị: {unit}</p>
        </div>
        <span
          aria-hidden="true"
          className="h-2.5 w-2.5 rounded-full shadow-[0_0_14px_currentColor]"
          style={{ backgroundColor: color, color }}
        />
      </div>

      <div
        aria-label={`Biểu đồ ${title.toLocaleLowerCase('vi-VN')} theo thời gian`}
        className="h-56 w-full"
        role="img"
      >
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -18 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.28} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            <XAxis
              dataKey="timestampMs"
              domain={['dataMin', 'dataMax']}
              minTickGap={34}
              scale="time"
              stroke="var(--chart-axis)"
              tick={{ fill: 'var(--chart-axis)', fontSize: 10 }}
              tickFormatter={(value: number) => axisTimeFormatter.format(new Date(value))}
              tickLine={false}
              type="number"
            />
            <YAxis
              domain={['auto', 'auto']}
              stroke="var(--chart-axis)"
              tick={{ fill: 'var(--chart-axis)', fontSize: 10 }}
              tickFormatter={(value: number) => formatMeasurement(value)}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--tooltip-background)',
                border: '1px solid var(--tooltip-border)',
                borderRadius: '12px',
                boxShadow: '0 16px 40px rgba(0, 0, 0, 0.3)',
                fontSize: '12px',
              }}
              cursor={{ stroke: 'rgba(148, 163, 184, 0.24)' }}
              formatter={(value) => [`${formatMeasurement(Number(value))} ${unit}`, title]}
              labelFormatter={(value) => fullTimeFormatter.format(new Date(Number(value)))}
              labelStyle={{ color: 'var(--tooltip-label)', marginBottom: '6px' }}
            />
            <Area
              connectNulls={false}
              dataKey={dataKey}
              fill={`url(#${gradientId})`}
              isAnimationActive={false}
              name={title}
              stroke={color}
              strokeWidth={2}
              type="monotone"
              unit={` ${unit}`}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </article>
  )
}

export function TelemetryHistoryPanel({ history }: TelemetryHistoryPanelProps) {
  const [selectedBucket, setSelectedBucket] = useState<Bucket>('5m')
  const selectedHistory = history[selectedBucket] as TelemetryHistoryResponse
  const points = useMemo(() => normalizeTelemetryHistory(selectedHistory), [selectedHistory])
  const selectedOption = bucketOptions.find((option) => option.value === selectedBucket)
  const firstTimestamp = points.at(0)?.timestampMs
  const lastTimestamp = points.at(-1)?.timestampMs

  return (
    <section aria-labelledby="history-heading" className="pb-8" id="history">
      <div className="panel-card overflow-hidden p-5 sm:p-6">
        <div className="flex flex-col gap-5 border-b border-slate-200/80 pb-6 dark:border-white/[0.07] xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
              <ChartNoAxesCombined aria-hidden="true" className="h-4 w-4" />
              <p className="eyebrow !text-emerald-700/75 dark:!text-emerald-400/75">Dữ liệu theo thời gian</p>
            </div>
            <h2 id="history-heading" className="mt-2 text-xl font-semibold tracking-tight text-slate-950 dark:text-white">
              Lịch sử môi trường
            </h2>
            <p className="mt-2 text-xs leading-5 text-slate-600 dark:text-slate-400">
              {points.length > 0 && firstTimestamp !== undefined && lastTimestamp !== undefined
                ? `${points.length} điểm · ${fullTimeFormatter.format(new Date(firstTimestamp))} – ${fullTimeFormatter.format(new Date(lastTimestamp))}`
                : 'Chưa có dữ liệu trong khoảng thời gian này'}
            </p>
          </div>

          <div>
            <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
              Độ phân giải
            </p>
            <div
              aria-label="Chọn độ phân giải biểu đồ"
              className="inline-flex flex-wrap gap-1 rounded-xl border border-slate-200/80 bg-slate-100/80 p-1 dark:border-white/[0.07] dark:bg-black/20"
              role="group"
            >
              {bucketOptions.map((option) => {
                const selected = option.value === selectedBucket

                return (
                  <button
                    aria-label={`Xem ${option.description.toLocaleLowerCase('vi-VN')}`}
                    aria-pressed={selected}
                    className={`rounded-lg px-3 py-2 text-xs font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300 ${
                      selected
                        ? 'bg-white text-emerald-800 shadow-sm dark:bg-emerald-400/15 dark:text-emerald-200 dark:shadow-none'
                        : 'text-slate-600 hover:bg-white/70 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/[0.04] dark:hover:text-slate-100'
                    }`}
                    key={option.value}
                    onClick={() => setSelectedBucket(option.value)}
                    type="button"
                  >
                    {option.label}
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {points.length > 0 ? (
          <>
            <div className="mt-6 grid gap-4 xl:grid-cols-3">
              <MetricChart
                color="#fb923c"
                data={points}
                dataKey="temperatureC"
                title="Nhiệt độ"
                unit="°C"
              />
              <MetricChart
                color="#38bdf8"
                data={points}
                dataKey="humidityPct"
                title="Độ ẩm"
                unit="%"
              />
              <MetricChart
                color="#fcd34d"
                data={points}
                dataKey="lightLux"
                title="Cường độ sáng"
                unit="lux"
              />
            </div>

            <div className="mt-4 flex items-start gap-2 rounded-xl border border-slate-200/80 bg-slate-50/80 px-4 py-3 text-xs leading-5 text-slate-600 dark:border-white/[0.06] dark:bg-white/[0.02] dark:text-slate-400">
              <CircleAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" />
              <p>
                Đang xem <span className="font-semibold text-slate-800 dark:text-slate-300">{selectedOption?.description}</span>.
                Khoảng trống trên đường biểu diễn là giá trị cảm biến <code>null</code>, không được đổi thành 0.
              </p>
            </div>
          </>
        ) : (
          <div className="grid min-h-72 place-items-center py-12 text-center">
            <div>
              <ChartNoAxesCombined aria-hidden="true" className="mx-auto h-8 w-8 text-slate-400 dark:text-slate-500" />
              <p className="mt-4 text-sm font-semibold text-slate-700 dark:text-slate-300">Chưa có dữ liệu lịch sử</p>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">Hãy thử một độ phân giải hoặc khoảng thời gian khác.</p>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
