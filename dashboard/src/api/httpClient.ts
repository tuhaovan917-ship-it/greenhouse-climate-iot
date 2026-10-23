import { dashboardConfig } from './config'
import { expireActiveAuth, getCsrfToken, isSecureDashboardMode } from './authSession'

interface RequestOptions extends RequestInit {
  authenticated?: boolean
}

interface ErrorPayload {
  detail?: string
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function apiRequest<T>(
  path: string,
  { authenticated = false, headers, ...options }: RequestOptions = {},
): Promise<T> {
  const requestHeaders = new Headers(headers)
  requestHeaders.set('Accept', 'application/json')

  if (options.body !== undefined) {
    requestHeaders.set('Content-Type', 'application/json')
  }

  const secure = isSecureDashboardMode()
  const method = (options.method ?? 'GET').toUpperCase()
  if (secure && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = getCsrfToken()
    if (!csrf) throw new ApiError(401, 'Chưa có phiên đăng nhập để gửi yêu cầu điều khiển.')
    requestHeaders.set('X-CSRF-Token', csrf)
  }
  if (!secure && authenticated && dashboardConfig.apiKey) {
    requestHeaders.set('X-API-Key', dashboardConfig.apiKey)
  }

  const response = await fetch(new URL(path, dashboardConfig.apiBaseUrl), {
    ...options,
    credentials: 'include',
    headers: requestHeaders,
  })

  if (!response.ok) {
    if (secure && response.status === 401) expireActiveAuth()
    let message = `Backend trả về lỗi HTTP ${response.status}`

    try {
      const payload = (await response.json()) as ErrorPayload
      if (typeof payload.detail === 'string' && payload.detail.trim()) {
        message = payload.detail
      }
    } catch {
      // Giữ thông báo HTTP khi response không phải JSON.
    }

    throw new ApiError(response.status, message)
  }

  return (await response.json()) as T
}
