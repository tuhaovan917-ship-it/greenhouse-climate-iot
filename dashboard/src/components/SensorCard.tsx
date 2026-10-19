import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

interface SensorCardProps {
  title: string
  value: string
  unit?: string
  helper: ReactNode
  icon: LucideIcon
  accentClass: string
  valueLabel?: string
}

export function SensorCard({
  title,
  value,
  unit,
  helper,
  icon: Icon,
  accentClass,
  valueLabel,
}: SensorCardProps) {
  return (
    <article className="panel-card group relative min-h-48 overflow-hidden p-5 sm:p-6">
      <div
        aria-hidden="true"
        className={`absolute -right-8 -top-8 h-28 w-28 rounded-full opacity-15 blur-3xl transition-opacity duration-300 group-hover:opacity-25 ${accentClass}`}
      />

      <div className="relative flex h-full flex-col justify-between gap-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow">Cảm biến</p>
            <h2 className="mt-2 text-sm font-medium text-slate-700 dark:text-slate-300">{title}</h2>
          </div>
          <span className="icon-tile">
            <Icon aria-hidden="true" className="h-5 w-5" />
          </span>
        </div>

        <div>
          <p
            aria-label={valueLabel ?? `${title}: ${value}${unit ? ` ${unit}` : ''}`}
            className="flex items-end gap-1.5"
          >
            <span className="text-3xl font-semibold tracking-[-0.04em] text-slate-950 dark:text-white sm:text-4xl">
              {value}
            </span>
            {unit ? (
              <span className="mb-1 text-sm font-medium text-slate-500 dark:text-slate-400">{unit}</span>
            ) : null}
          </p>
          <div className="mt-3 text-xs leading-5 text-slate-600 dark:text-slate-400">{helper}</div>
        </div>
      </div>
    </article>
  )
}
