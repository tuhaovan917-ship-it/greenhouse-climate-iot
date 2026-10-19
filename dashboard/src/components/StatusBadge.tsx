import type { ReactNode } from 'react'

type StatusTone = 'positive' | 'warning' | 'critical' | 'neutral'

interface StatusBadgeProps {
  children: ReactNode
  tone?: StatusTone
  showDot?: boolean
}

const toneClasses: Record<StatusTone, string> = {
  positive:
    'border-emerald-600/20 bg-emerald-100/80 text-emerald-800 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300',
  warning:
    'border-amber-600/20 bg-amber-100/80 text-amber-800 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-200',
  critical:
    'border-red-600/20 bg-red-100/80 text-red-800 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-200',
  neutral:
    'border-slate-300/80 bg-slate-100/80 text-slate-700 dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-300',
}

const dotClasses: Record<StatusTone, string> = {
  positive: 'bg-emerald-400',
  warning: 'bg-amber-300',
  critical: 'bg-red-400',
  neutral: 'bg-slate-400',
}

export function StatusBadge({
  children,
  tone = 'neutral',
  showDot = false,
}: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold tracking-wide ${toneClasses[tone]}`}
    >
      {showDot ? (
        <span
          aria-hidden="true"
          className={`h-1.5 w-1.5 rounded-full shadow-[0_0_10px_currentColor] ${dotClasses[tone]}`}
        />
      ) : null}
      {children}
    </span>
  )
}
