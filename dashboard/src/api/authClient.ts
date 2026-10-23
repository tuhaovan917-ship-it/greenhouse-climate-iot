/** A5.1 login preview client. A5.2 will reuse this for the real app gate. */
import { dashboardConfig } from './config'

export interface AuthUser {
  id: string
  username: string
  email: string
  role: 'admin' | 'operator' | 'viewer'
  isActive: boolean
}

export interface AuthResponse {
  user: AuthUser
  csrfToken: string
}

async function authRequest<T>(path: string, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  const response = await fetch(new URL(path, dashboardConfig.apiBaseUrl), {
    ...init,
    credentials: 'include',
    headers,
  })
  if (!response.ok) {
    if (response.status === 401) throw new Error(path.endsWith('/login') ? 'Tài khoản hoặc mật khẩu không đúng.' : 'Phiên đăng nhập không hợp lệ hoặc đã hết hạn.')
    if (response.status === 429) throw new Error('Quá nhiều lần thử đăng nhập. Hãy thử lại sau.')
    if (response.status === 403) throw new Error('Yêu cầu bị từ chối do chính sách bảo mật.')
    throw new Error(`Backend trả về HTTP ${response.status}.`)
  }
  return response.json() as Promise<T>
}

export function login(username: string, password: string) {
  return authRequest<AuthResponse>('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function me() {
  return authRequest<AuthResponse>('/api/auth/me', { method: 'GET' })
}

export function logout(csrfToken: string) {
  return authRequest<{ status: 'logged_out' }>('/api/auth/logout', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
  })
}
