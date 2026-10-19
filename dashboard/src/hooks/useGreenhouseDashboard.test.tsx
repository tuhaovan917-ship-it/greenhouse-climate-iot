import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fixtureAlerts,
  fixtureCommandHistory,
  fixtureDeviceConfig,
  fixtureDeviceState,
  fixtureTelemetry,
  fixtureTelemetryHistoryByBucket,
} from '../test/fixtures'
import { useGreenhouseDashboard } from './useGreenhouseDashboard'

const apiMocks = vi.hoisted(() => ({
  getAlerts: vi.fn(),
  getCommands: vi.fn(),
  getDeviceConfig: vi.fn(),
  getDeviceState: vi.fn(),
  getLatestTelemetry: vi.fn(),
  getTelemetryHistory: vi.fn(),
  postCommand: vi.fn(),
  postDeviceConfig: vi.fn(),
}))

vi.mock('../api/greenhouseApi', () => ({
  ...apiMocks,
  withMode: (config: Record<string, unknown>, mode: 'AUTO' | 'MANUAL') => ({
    ...config,
    mode,
  }),
}))

class FakeWebSocket {
  static readonly OPEN = 1
  static instances: FakeWebSocket[] = []

  readonly url: string
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  send = vi.fn()

  constructor(url: string | URL) {
    this.url = String(url)
    FakeWebSocket.instances.push(this)
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  message(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>)
  }

  disconnect() {
    this.readyState = 3
    this.onclose?.()
  }

  close() {
    this.readyState = 3
    this.onclose?.()
  }
}

beforeEach(() => {
  FakeWebSocket.instances = []
  vi.clearAllMocks()
  vi.stubGlobal('WebSocket', FakeWebSocket)

  apiMocks.getLatestTelemetry.mockResolvedValue(fixtureTelemetry)
  apiMocks.getDeviceState.mockResolvedValue(fixtureDeviceState)
  apiMocks.getDeviceConfig.mockResolvedValue(fixtureDeviceConfig)
  apiMocks.getCommands.mockResolvedValue({ data: fixtureCommandHistory })
  apiMocks.getAlerts.mockResolvedValue({ data: fixtureAlerts })
  apiMocks.getTelemetryHistory.mockImplementation(
    ({ bucket }: { bucket: keyof typeof fixtureTelemetryHistoryByBucket }) =>
      Promise.resolve(fixtureTelemetryHistoryByBucket[bucket]),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useGreenhouseDashboard', () => {
  it('chỉ tải bucket được chọn với from/to và không reconnect WebSocket', async () => {
    const { result, unmount } = renderHook(() =>
      useGreenhouseDashboard({ deviceId: 'greenhouse-01', enabled: true }),
    )

    await waitFor(() => expect(result.current.status).toBe('ready'))
    await waitFor(() => expect(apiMocks.getTelemetryHistory).toHaveBeenCalled())
    expect(apiMocks.getTelemetryHistory).toHaveBeenLastCalledWith(
      expect.objectContaining({
        deviceId: 'greenhouse-01',
        bucket: '5m',
        limit: 1_000,
        order: 'asc',
        from: expect.any(String),
        to: expect.any(String),
      }),
    )

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    act(() => result.current.updateHistoryQuery({ bucket: '1m', range: '6h' }))

    await waitFor(() => expect(apiMocks.getTelemetryHistory).toHaveBeenLastCalledWith(
      expect.objectContaining({ bucket: '1m' }),
    ))
    expect(FakeWebSocket.instances).toHaveLength(1)

    unmount()
  })

  it('vẫn sẵn sàng khi hệ thống mới chưa có telemetry', async () => {
    apiMocks.getLatestTelemetry.mockResolvedValue(null)

    const { result, unmount } = renderHook(() =>
      useGreenhouseDashboard({ deviceId: 'greenhouse-01', enabled: true }),
    )

    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(result.current.telemetry).toBeNull()
    expect(result.current.deviceState).toEqual(fixtureDeviceState)

    unmount()
  })

  it('nhận state qua WebSocket và chuyển sang polling khi socket mất', async () => {
    const { result, unmount } = renderHook(() =>
      useGreenhouseDashboard({ deviceId: 'greenhouse-01', enabled: true }),
    )

    await waitFor(() => expect(result.current.status).toBe('ready'))
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))

    const socket = FakeWebSocket.instances[0]
    act(() => socket.open())
    expect(result.current.realtimeStatus).toBe('connected')

    const manualState = { ...fixtureDeviceState, mode: 'MANUAL' as const, fan: false }
    act(() => socket.message({ type: 'state', data: manualState }))
    expect(result.current.deviceState).toEqual(manualState)

    act(() => socket.message({ type: 'ping' }))
    expect(result.current.deviceState).toEqual(manualState)
    expect(socket.send).not.toHaveBeenCalled()

    const requestsBeforeDisconnect = apiMocks.getLatestTelemetry.mock.calls.length
    act(() => socket.disconnect())

    expect(result.current.realtimeStatus).toBe('polling')
    await waitFor(() =>
      expect(apiMocks.getLatestTelemetry.mock.calls.length).toBeGreaterThan(
        requestsBeforeDisconnect,
      ),
    )

    unmount()
  })
})
