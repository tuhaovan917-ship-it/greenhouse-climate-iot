import { Leaf, LoaderCircle, RefreshCw, ServerOff } from 'lucide-react'
import { dashboardConfig } from './api/config'
import { isSecureDashboardMode } from './api/authSession'
import { SecureDashboard } from './features/auth/SecureDashboard'
import { LoginPreview } from './features/auth/LoginPreview'
import { OverviewPage } from './features/overview/OverviewPage'
import { useGreenhouseDashboard } from './hooks/useGreenhouseDashboard'

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

function DashboardApp({ readOnly = false }: { readOnly?: boolean } = {}) {
  const dashboard = useGreenhouseDashboard({
    deviceId: dashboardConfig.deviceId,
    enabled: true,
  })

  if (dashboard.status === 'error') {
    return <DashboardLoadState error={dashboard.error} onRetry={() => void dashboard.retry()} />
  }

  if (
    dashboard.status !== 'ready' ||
    !dashboard.deviceState ||
    !dashboard.config
  ) {
    return <DashboardLoadState />
  }

  return (
    <OverviewPage
      controlReadOnly={readOnly}
      alerts={dashboard.alerts}
      control={{
        config: dashboard.config,
        commands: dashboard.commands,
        onPublishConfig: dashboard.publishConfig,
        onPublishMode: dashboard.publishMode,
        onSendCommand: dashboard.sendCommand,
      }}
      deviceState={dashboard.deviceState}
      history={dashboard.history}
      historyError={dashboard.historyError}
      historyLoading={dashboard.historyLoading}
      onHistoryQueryChange={dashboard.updateHistoryQuery}
      onRetryHistory={() => void dashboard.refreshHistory()}
      realtimeStatus={dashboard.realtimeStatus}
      telemetry={dashboard.telemetry}
    />
  )
}

// Strict authentication takes precedence over legacy preview routes.
export default function App() {
  if (isSecureDashboardMode()) {
    return (
      <SecureDashboard renderDashboard={(user) => (
        <DashboardApp readOnly={user.role === 'viewer'} />
      )} />
    )
  }
  if (new URLSearchParams(window.location.search).get('preview') === 'login') {
    return <LoginPreview />
  }
  return <DashboardApp />
}
