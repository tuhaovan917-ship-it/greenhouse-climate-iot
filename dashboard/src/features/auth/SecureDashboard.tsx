import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Leaf, LockKeyhole, LogOut, RefreshCw } from 'lucide-react'
import { AuthApiError, login, logout, me, type AuthResponse, type AuthUser } from '../../api/authClient'
import { SESSION_EXPIRED_EVENT, setActiveAuth } from '../../api/authSession'
import { LoginPage } from './LoginPage'
import './secureDashboard.css'

type AuthPhase = 'checking' | 'anonymous' | 'ready' | 'unavailable'

interface SecureDashboardProps {
  renderDashboard: (user: AuthUser) => ReactNode
}

const roleNames: Record<AuthUser['role'], string> = {
  admin: 'Quản trị viên',
  operator: 'Người vận hành',
  viewer: 'Người xem',
}

export function SecureDashboard({ renderDashboard }: SecureDashboardProps) {
  const [phase, setPhase] = useState<AuthPhase>('checking')
  const [auth, setAuth] = useState<AuthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [signingOut, setSigningOut] = useState(false)

  const restoreSession = useCallback(async () => {
    setPhase('checking')
    setError(null)
    try {
      const result = await me()
      setActiveAuth(result)
      setAuth(result)
      setPhase('ready')
    } catch (reason) {
      setActiveAuth(null)
      setAuth(null)
      if (reason instanceof AuthApiError && reason.status === 401) {
        setPhase('anonymous')
      } else {
        setError(reason instanceof Error ? reason.message : 'Không thể kiểm tra phiên đăng nhập.')
        setPhase('unavailable')
      }
    }
  }, [])

  useEffect(() => {
    // Do not accidentally load telemetry or start a WebSocket before /me succeeds.
    let mounted = true
    void me().then((result) => {
      if (!mounted) return
      setActiveAuth(result)
      setAuth(result)
      setPhase('ready')
    }).catch((reason: unknown) => {
      if (!mounted) return
      if (reason instanceof AuthApiError && reason.status === 401) {
        setPhase('anonymous')
      } else {
        setError(reason instanceof Error ? reason.message : 'Không thể kiểm tra phiên đăng nhập.')
        setPhase('unavailable')
      }
    })
    return () => {
      mounted = false
      setActiveAuth(null)
    }
  }, [])

  useEffect(() => {
    const expired = () => {
      setActiveAuth(null)
      setAuth(null)
      setPhase('anonymous')
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, expired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expired)
  }, [])

  useEffect(() => {
    if (phase !== 'ready') return
    // Auth is revalidated periodically even when no REST requests are made.
    let current = true
    const check = async () => {
      try {
        const latest = await me()
        if (!current) return
        setActiveAuth(latest)
        setAuth(latest)
      } catch (reason) {
        if (!current) return
        if (reason instanceof AuthApiError && reason.status === 401) {
          setActiveAuth(null)
          setAuth(null)
          setPhase('anonymous')
        }
        // On temporary network errors, retain the UI. Protected API/WS calls
        // will still fail closed at the Backend until the connection recovers.
      }
    }
    window.addEventListener('focus', check)
    const interval = window.setInterval(() => { void check() }, 60_000)
    return () => {
      current = false
      window.removeEventListener('focus', check)
      window.clearInterval(interval)
    }
  }, [phase])

  async function signIn(username: string, password: string) {
    const result = await login(username, password)
    setActiveAuth(result)
    setAuth(result)
    setPhase('ready')
    setError(null)
  }

  async function signOut() {
    if (!auth || signingOut) return
    setSigningOut(true)
    setError(null)
    try {
      await logout(auth.csrfToken)
      setActiveAuth(null)
      setAuth(null)
      setPhase('anonymous')
    } catch (reason) {
      if (reason instanceof AuthApiError && reason.status === 401) {
        setActiveAuth(null)
        setAuth(null)
        setPhase('anonymous')
      } else {
        setError(reason instanceof Error ? reason.message : 'Không thể đăng xuất.')
      }
    } finally {
      setSigningOut(false)
    }
  }

  if (phase === 'checking') {
    return (
      <main className="ghs-centered" role="status">
        <span className="ghs-mark"><Leaf aria-hidden="true" size={24} /></span>
        <p>Đang kiểm tra quyền truy cập…</p>
      </main>
    )
  }

  if (phase === 'unavailable') {
    return (
      <main className="ghs-centered">
        <LockKeyhole aria-hidden="true" size={28} />
        <h1>Không kiểm tra được phiên đăng nhập</h1>
        <p role="alert">{error}</p>
        <button onClick={() => { void restoreSession() }} type="button">
          <RefreshCw aria-hidden="true" size={16} /> Kiểm tra lại
        </button>
      </main>
    )
  }

  if (phase === 'anonymous' || !auth) {
    return <LoginPage onLogin={signIn} />
  }

  const canControl = auth.user.role === 'operator' || auth.user.role === 'admin'

  return (
    <div className="ghs-authenticated">
      <header className="ghs-session-bar" aria-label="Phiên đăng nhập">
        <div className="ghs-session-brand"><Leaf aria-hidden="true" size={17} /> GREENHOUSE <span> / TRUY CẬP AN TOÀN</span></div>
        <div className="ghs-session-actions">
          <span className="ghs-account" aria-label={`Tài khoản ${auth.user.username}, vai trò ${roleNames[auth.user.role]}`}>
            <strong>{auth.user.username}</strong><span>{roleNames[auth.user.role]}</span>
          </span>
          <button type="button" onClick={() => { void signOut() }} disabled={signingOut}>
            <LogOut aria-hidden="true" size={16} /> {signingOut ? 'Đang đăng xuất…' : 'Đăng xuất'}
          </button>
        </div>
      </header>
      {error ? <p className="ghs-logout-error" role="alert">{error}</p> : null}
      {!canControl ? <div className="ghs-viewer-notice">Chế độ chỉ xem · Tài khoản Viewer không thể gửi lệnh hoặc thay đổi ngưỡng.</div> : null}
      {renderDashboard(auth.user)}
    </div>
  )
}
