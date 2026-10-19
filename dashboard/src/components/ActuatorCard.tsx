import type { LucideIcon } from 'lucide-react'

interface ActuatorCardProps {
  name: string
  description: string
  active: boolean
  icon: LucideIcon
}

export function ActuatorCard({
  name,
  description,
  active,
  icon: Icon,
}: ActuatorCardProps) {
  return (
    <article className="flex items-center gap-4 rounded-2xl border border-slate-200/80 bg-white/55 p-4 transition-colors hover:border-slate-300 hover:bg-white/90 dark:border-white/[0.07] dark:bg-white/[0.025] dark:hover:border-white/15 dark:hover:bg-white/[0.045]">
      <span
        className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl border ${
          active
            ? 'border-emerald-600/20 bg-emerald-100/80 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300'
            : 'border-slate-200 bg-slate-100 text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400'
        }`}
      >
        <Icon aria-hidden="true" className="h-5 w-5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-3">
          <h3 className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{name}</h3>
          <span
            className={`text-[0.65rem] font-bold tracking-[0.18em] ${
              active
                ? 'text-emerald-700 dark:text-emerald-300'
                : 'text-slate-500 dark:text-slate-400'
            }`}
          >
            {active ? 'ĐANG BẬT' : 'ĐANG TẮT'}
          </span>
        </div>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{description}</p>
      </div>
    </article>
  )
}
