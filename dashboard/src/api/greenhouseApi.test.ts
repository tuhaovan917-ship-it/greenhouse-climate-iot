import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getConfigStatus,
  getLatestTelemetry,
  getTelemetryHistory,
  postCommand,
  postDeviceConfig,
} from './greenhouseApi'
import { ApiError } from './httpClient'
import { fixtureDeviceConfig } from '../test/fixtures'
import { setActiveAuth } from './authSession'

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

beforeEach(() => {
  setActiveAuth({
    csrfToken: 'test-csrf-token',
    user: { id: 'test', username: 'test', email: 'test@example.test', role: 'operator', isActive: true },
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  setActiveAuth(null)
})

describe('greenhouseApi', () => {
  it('chấp nhận latest telemetry null khi database chưa có dữ liệu', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(null)))

    await expect(getLatestTelemetry('greenhouse-01')).resolves.toBeNull()
  })

  it('gửi đúng query lịch sử theo semantics của Backend', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ bucket: '5m', data: [] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await getTelemetryHistory({
      deviceId: 'greenhouse-01',
      bucket: '5m',
      from: '2026-10-19T00:00:00Z',
      to: '2026-10-20T00:00:00Z',
      limit: 80,
      order: 'asc',
    })

    const requestUrl = new URL(String(fetchMock.mock.calls[0][0]))
    expect(requestUrl.pathname).toBe('/api/telemetry')
    expect(Object.fromEntries(requestUrl.searchParams)).toMatchObject({
      deviceId: 'greenhouse-01',
      bucket: '5m',
      from: '2026-10-19T00:00:00Z',
      to: '2026-10-20T00:00:00Z',
      limit: '80',
      order: 'asc',
    })
  })

  it('gửi command JSON và chỉ tạo PENDING từ response 202', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ commandId: 'cmd-123', status: 'PENDING' }, { status: 202 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await postCommand({
      deviceId: 'greenhouse-01',
      device: 'fan',
      on: true,
    })

    expect(result).toEqual({ commandId: 'cmd-123', status: 'PENDING' })
    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect(options.method).toBe('POST')
    expect(options.body).toBe(JSON.stringify({
      deviceId: 'greenhouse-01',
      device: 'fan',
      on: true,
    }))
  })

  it('giữ configId và PENDING từ POST config 202', async () => {
    const payload = {
      configId: 'cfg-ui-001',
      status: 'PENDING',
      config: fixtureDeviceConfig,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(payload, { status: 202 })))

    await expect(postDeviceConfig('greenhouse-01', fixtureDeviceConfig)).resolves.toEqual(payload)
  })

  it('lấy trạng thái Config ACK bằng configId', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      configId: 'cfg-ui-001',
      deviceId: 'greenhouse-01',
      status: 'APPLIED',
      reason: null,
      wasLate: false,
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getConfigStatus('cfg-ui-001')).resolves.toMatchObject({
      configId: 'cfg-ui-001',
      deviceId: 'greenhouse-01',
      status: 'APPLIED',
      wasLate: false,
    })
    const requestUrl = new URL(String(fetchMock.mock.calls[0][0]))
    expect(requestUrl.pathname).toBe('/api/config/status')
    expect(requestUrl.searchParams.get('configId')).toBe('cfg-ui-001')
  })

  it('giữ detail của lỗi REST để giao diện giải thích đúng nguyên nhân', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: 'Thiet bi dang offline' }, { status: 409 }),
      ),
    )

    await expect(
      postCommand({ deviceId: 'greenhouse-01', device: 'fan', on: true }),
    ).rejects.toEqual(new ApiError(409, 'Thiet bi dang offline'))
  })
})
