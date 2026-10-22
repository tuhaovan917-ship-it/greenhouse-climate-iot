import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'

type Theme = 'light' | 'dark'

const themeStorageKey = 'greenhouse-theme'

function getInitialTheme(): Theme {
  const storedTheme = window.localStorage.getItem(themeStorageKey)

  if (storedTheme === 'light' || storedTheme === 'dark') {
    return storedTheme
  }

  return window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

function applyTheme(theme: Theme) {
  const isDark = theme === 'dark'
  const root = document.documentElement
  const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')

  root.classList.toggle('dark', isDark)
  root.style.colorScheme = theme
  window.localStorage.setItem(themeStorageKey, theme)

  if (themeColor) {
    themeColor.content = isDark ? '#07110e' : '#f3f7f4'
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme)
  const isDark = theme === 'dark'

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  return (
    <button
      aria-checked={isDark}
      aria-label={isDark ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối'}
      className="group inline-flex h-10 min-w-28 items-center justify-between gap-2.5 rounded-full border border-slate-300 bg-white px-3 text-slate-800 shadow-sm transition-colors hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:shadow-none dark:hover:border-slate-500 dark:hover:bg-slate-800"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      role="switch"
      type="button"
    >
      <span className="inline-flex items-center gap-1.5">
        {isDark ? (
          <Moon aria-hidden="true" className="h-4 w-4 text-indigo-300" />
        ) : (
          <Sun aria-hidden="true" className="h-4 w-4 text-amber-600" />
        )}
        <span className="text-xs font-bold">{isDark ? 'Tối' : 'Sáng'}</span>
      </span>
      <span
        aria-hidden="true"
        className="relative h-5 w-9 shrink-0 rounded-full border border-slate-300 bg-slate-200 shadow-inner transition-colors dark:border-slate-500 dark:bg-slate-600"
        data-testid="theme-switch-track"
      >
        <span
          className={`absolute left-0.5 top-0.5 h-3.5 w-3.5 rounded-full shadow-sm ring-1 transition-transform duration-200 ${
            isDark
              ? 'translate-x-4 bg-indigo-100 ring-indigo-300/60'
              : 'translate-x-0 bg-white ring-slate-300'
          }`}
          data-testid="theme-switch-thumb"
        />
      </span>
    </button>
  )
}
