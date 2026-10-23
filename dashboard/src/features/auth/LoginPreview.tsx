import { useEffect, useState } from 'react'
import { CheckCircle2, Leaf } from 'lucide-react'
import { login, logout, me, type AuthResponse } from '../../api/authClient'
import { LoginPage } from './LoginPage'

/** Isolated visual + real login preview. The operational dashboard is not mounted here. */
export function LoginPreview() {
  const [session, setSession] = useState<AuthResponse | null>(null)
  const [checking, setChecking] = useState(true)
  const [signingOut, setSigningOut] = useState(false)
  const [logoutError, setLogoutError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void me().then((result) => {
      if (active) setSession(result)
    }).catch(() => {
      // Anonymous or backend unavailable: show login form.
    }).finally(() => {
      if (active) setChecking(false)
    })
    return () => { active = false }
  }, [])

  async function signOut() {
    if (!session || signingOut) return
    setSigningOut(true)
    setLogoutError(null)
    try {
      await logout(session.csrfToken)
      setSession(null)
    } catch (reason) {
      setLogoutError(reason instanceof Error ? reason.message : 'Không thể đăng xuất.')
    } finally {
      setSigningOut(false)
    }
  }

  if (checking) {
    return <main className="ghl-preview-result"><div role="status">Đang kiểm tra phiên đăng nhập…</div></main>
  }

  return (
    <>
      <div className="ghl-preview-label">A5.1 · LOGIN PREVIEW</div>
      {session ? (
        <main className="ghl-preview-result">
          <div className="ghl-result-card">
            <Leaf size={24} aria-hidden="true" />
            <h2>Đã xác thực thành công.</h2>
            <p><CheckCircle2 size={17} aria-hidden="true" style={{ display: 'inline', verticalAlign: 'middle', marginRight: 7 }} />Backend đã tạo phiên đăng nhập hợp lệ.</p>
            <p><strong>Tài khoản:</strong> {session.user.username}<br /><strong>Vai trò:</strong> {session.user.role}</p>
            <p>Đây là trang xem trước A5.1. Bước A5.2 sẽ kết nối phiên đăng nhập với Dashboard chính.</p>
            {logoutError ? <p role="alert">{logoutError}</p> : null}
            <button type="button" disabled={signingOut} onClick={() => { void signOut() }}>{signingOut ? 'Đang đăng xuất…' : 'Đăng xuất'}</button>
            <a href="/">Về Dashboard hiện tại</a>
          </div>
        </main>
      ) : (
        <LoginPage onLogin={async (username, password) => { setSession(await login(username, password)) }} />
      )}
    </>
  )
}
