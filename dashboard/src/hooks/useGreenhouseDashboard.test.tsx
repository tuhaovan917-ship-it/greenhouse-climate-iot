import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  mockAlerts,
  mockCommandHistory,
  mockDeviceConfig,
  mockDeviceState,
  mockTelemetry,
  mockTelemetryHistoryByBucket,
} from '../mocks/greenhouse'
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

  apiMocks.getLatestTelemetry.mockResolvedValue(mockTelemetry)
  apiMocks.getDeviceState.mockResolvedValue(mockDeviceState)
  apiMocks.getDeviceConfig.mockResolvedValue(mockDeviceConfig)
  apiMocks.getCommands.mockResolvedValue({ data: mockCommandHistory })
  apiMocks.getAlerts.mockResolvedValue({ data: mockAlerts })
  apiMocks.getTelemetryHistory.mockImplementation(
    ({ bucket }: { bucket: keyof typeof mockTelemetryHistoryByBucket }) =>
      Promise.resolve(mockTelemetryHistoryByBucket[bucket]),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useGreenhouseDashboard', () => {
  it('nhận state qua WebSocket và chuyển sang polling khi socket mất', async () => {
    const { result, unmount } = renderHook(() =>
      useGreenhouseDashboard({ deviceId: 'greenhouse-01', enabled: true }),
    )

    await waitFor(() => expect(result.current.status).toBe('ready'))
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))

    const socket = FakeWebSocket.instances[0]
    act(() => socket.open())
    expect(result.current.realtimeStatus).toBe('connected')

    const manualState = { ...mockDeviceState, mode: 'MANUAL' as const, fan: false }
    act(() => socket.message({ type: 'state', data: manualState }))
    expect(result.current.deviceState).toEqual(manualState)

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
