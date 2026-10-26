import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiRequest, ApiError } from './httpClient'
import { getCsrfToken, setActiveAuth, SESSION_EXPIRED_EVENT } from './authSession'

const auth = { user: { id: '1', username: 'operator', email: 'operator@example.test', role: 'operator' as const, isActive: true }, csrfToken: 'demo-test-csrf-token' }
const response = (status = 200) => new Response(JSON.stringify(status === 200 ? { ok: true } : { detail: 'Authentication required' }), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  window.history.replaceState({}, '', '/?preview=secure')
  setActiveAuth(auth)
})

afterEach(() => {
  setActiveAuth(null)
  window.history.replaceState({}, '', '/')
  vi.unstubAllGlobals()
})

describe('A5.2 secure REST transport', () => {
  it('includes credentials and csrf header on mutation', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response())
    vi.stubGlobal('fetch', fetchMock)
    await apiRequest('/api/commands', { authenticated: true, method: 'POST', body: JSON.stringify({ deviceId: 'greenhouse-01', device: 'fan', on: true }) })
    const request = fetchMock.mock.calls[0][1] as RequestInit
    const headers = new Headers(request.headers)
    expect(request.credentials).toBe('include')
    expect(headers.get('X-CSRF-Token')).toBe('demo-test-csrf-token')
    expect(headers.has('X-API-Key')).toBe(false)
  })

  it('includes cookie credentials on read without adding csrf', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response())
    vi.stubGlobal('fetch', fetchMock)
    await apiRequest('/api/state')
    const request = fetchMock.mock.calls[0][1] as RequestInit
    expect(request.credentials).toBe('include')
    expect(new Headers(request.headers).has('X-CSRF-Token')).toBe(false)
  })

  it('refuses mutation without memory-held csrf', async () => {
    setActiveAuth(null)
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await expect(apiRequest('/api/config', { method: 'POST', body: '{}' })).rejects.toEqual(new ApiError(401, 'Chưa có phiên đăng nhập để gửi yêu cầu điều khiển.'))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('clears csrf and emits expiry event on protected REST 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(401)))
    const expired = vi.fn()
    window.addEventListener(SESSION_EXPIRED_EVENT, expired, { once: true })
    await expect(apiRequest('/api/state')).rejects.toMatchObject({ status: 401 })
    expect(expired).toHaveBeenCalledTimes(1)
    expect(getCsrfToken()).toBeNull()
  })
})
