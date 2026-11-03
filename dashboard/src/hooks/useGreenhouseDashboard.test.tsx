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
  getConfigStatus: vi.fn(),
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
  apiMocks.getConfigStatus.mockResolvedValue({
    configId: 'cfg-ui-001',
    deviceId: 'greenhouse-01',
    status: 'PENDING',
    reason: null,
    wasLate: false,
  })
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

  it('không bỏ mất command_result đến trước REST 202', async () => {
    let resolveCommand: ((value: { commandId: string; status: 'PENDING' }) => void) | undefined
    apiMocks.postCommand.mockImplementation(
      () => new Promise((resolve) => {
        resolveCommand = resolve
      }),
    )

    const { result, unmount } = renderHook(() =>
      useGreenhouseDashboard({ deviceId: 'greenhouse-01', enabled: true }),
    )

    await waitFor(() => expect(result.current.status).toBe('ready'))
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))

    let request: Promise<void> | undefined
    act(() => {
      request = result.current.sendCommand({
        deviceId: 'greenhouse-01',
        device: 'fan',
        on: false,
      })
    })
    act(() => {
      FakeWebSocket.instances[0].message({
        type: 'command_result',
        data: {
          commandId: 'cmd-fast',
          result: 'APPLIED',
          wasLate: false,
        },
      })
    })
    await act(async () => {
      resolveCommand?.({ commandId: 'cmd-fast', status: 'PENDING' })
      await request
    })

    await waitFor(() => expect(
      result.current.commands.find((command) => command.commandId === 'cmd-fast'),
    ).toMatchObject({ status: 'APPLIED', requestedOn: false }))

    unmount()
  })

  it('đồng bộ lệnh PENDING với trạng thái cuối từ REST', async () => {
    apiMocks.postCommand.mockResolvedValue({
      commandId: 'cmd-rest-sync',
      status: 'PENDING',
    })

    const { result, unmount } = renderHook(() =>
      useGreenhouseDashboard({ deviceId: 'greenhouse-01', enabled: true }),
    )

    await waitFor(() => expect(result.current.status).toBe('ready'))
    apiMocks.getCommands.mockResolvedValue({
      data: [
        {
          commandId: 'cmd-rest-sync',
          deviceId: 'greenhouse-01',
          device: 'fan',
          requestedOn: false,
          status: 'APPLIED',
          reason: null,
          requestedAt: '2026-10-20T01:00:00Z',
          completedAt: '2026-10-20T01:00:01Z',
        },
        ...fixtureCommandHistory,
      ],
    })

    await act(async () => {
      await result.current.sendCommand({
        deviceId: 'greenhouse-01',
        device: 'fan',
        on: false,
      })
    })

    await waitFor(() => expect(
      result.current.commands.find((command) => command.commandId === 'cmd-rest-sync'),
    ).toMatchObject({ status: 'APPLIED' }))
    expect(apiMocks.getCommands.mock.calls.length).toBeGreaterThan(1)

    unmount()
  })

  it('tạo Config ACK PENDING, rồi áp dụng trạng thái cuối từ WebSocket', async () => {
    apiMocks.postDeviceConfig.mockResolvedValue({
      configId: 'cfg-ui-001',
      status: 'PENDING',
      config: fixtureDeviceConfig,
    })
    const { result, unmount } = renderHook(() =>
      useGreenhouseDashboard({ deviceId: 'greenhouse-01', enabled: true }),
    )
    await waitFor(() => expect(result.current.status).toBe('ready'))

    await act(async () => {
      await result.current.publishConfig(fixtureDeviceConfig)
    })
    expect(result.current.configAck).toMatchObject({
      configId: 'cfg-ui-001',
      status: 'PENDING',
    })

    const socket = FakeWebSocket.instances[0]
    act(() => socket.message({
      type: 'config_result',
      data: {
        configId: 'cfg-ui-001',
        result: 'REJECTED',
        reason: 'NVS_WRITE_FAILED',
        wasLate: false,
      },
    }))
    expect(result.current.configAck).toMatchObject({
      configId: 'cfg-ui-001',
      status: 'REJECTED',
      reason: 'NVS_WRITE_FAILED',
    })

    act(() => socket.message({
      type: 'config_result',
      data: {
        configId: 'cfg-ui-001',
        result: 'TIMEOUT',
        reason: null,
        wasLate: false,
      },
    }))
    expect(result.current.configAck?.status).toBe('TIMEOUT')

    act(() => socket.message({
      type: 'config_result',
      data: {
        configId: 'cfg-ui-001',
        result: 'APPLIED',
        reason: null,
        wasLate: true,
      },
    }))
    expect(result.current.configAck).toMatchObject({ status: 'APPLIED', wasLate: true })
    unmount()
  })

  it('giữ config_result đến trước REST 202', async () => {
    let resolveConfig: ((value: {
      configId: string
      status: 'PENDING'
      config: typeof fixtureDeviceConfig
    }) => void) | undefined
    apiMocks.postDeviceConfig.mockImplementation(() => new Promise((resolve) => {
      resolveConfig = resolve
    }))
    const { result, unmount } = renderHook(() =>
      useGreenhouseDashboard({ deviceId: 'greenhouse-01', enabled: true }),
    )
    await waitFor(() => expect(result.current.status).toBe('ready'))

    let request: Promise<unknown> | undefined
    act(() => { request = result.current.publishConfig(fixtureDeviceConfig) })
    act(() => FakeWebSocket.instances[0].message({
      type: 'config_result',
      data: {
        configId: 'cfg-fast',
        result: 'APPLIED',
        reason: null,
        wasLate: false,
      },
    }))
    await act(async () => {
      resolveConfig?.({ configId: 'cfg-fast', status: 'PENDING', config: fixtureDeviceConfig })
      await request
    })

    expect(result.current.configAck).toMatchObject({ configId: 'cfg-fast', status: 'APPLIED' })
    unmount()
  })

  it('không để REST snapshot cũ PENDING ghi đè ACK WebSocket terminal', async () => {
    apiMocks.postDeviceConfig.mockResolvedValue({
      configId: 'cfg-rest-race',
      status: 'PENDING',
      config: fixtureDeviceConfig,
    })
    let resolveStatus: ((value: {
      configId: string
      deviceId: string
      status: 'PENDING'
      reason: null
      wasLate: false
    }) => void) | undefined
    apiMocks.getConfigStatus.mockImplementation(() => new Promise((resolve) => {
      resolveStatus = resolve
    }))
    const { result, unmount } = renderHook(() =>
      useGreenhouseDashboard({ deviceId: 'greenhouse-01', enabled: true }),
    )
    await waitFor(() => expect(result.current.status).toBe('ready'))
    await act(async () => { await result.current.publishConfig(fixtureDeviceConfig) })
    await waitFor(() => expect(apiMocks.getConfigStatus).toHaveBeenCalledWith('cfg-rest-race'))

    act(() => FakeWebSocket.instances[0].message({
      type: 'config_result',
      data: { configId: 'cfg-rest-race', result: 'APPLIED', reason: null, wasLate: false },
    }))
    await act(async () => {
      resolveStatus?.({
        configId: 'cfg-rest-race',
        deviceId: 'greenhouse-01',
        status: 'PENDING',
        reason: null,
        wasLate: false,
      })
    })
    expect(result.current.configAck?.status).toBe('APPLIED')
    unmount()
  })

  it('dùng REST fallback cho trạng thái terminal và bỏ qua kết quả Config cũ', async () => {
    apiMocks.postDeviceConfig
      .mockResolvedValueOnce({ configId: 'cfg-old', status: 'PENDING', config: fixtureDeviceConfig })
      .mockResolvedValueOnce({ configId: 'cfg-new', status: 'PENDING', config: fixtureDeviceConfig })
    apiMocks.getConfigStatus.mockImplementation(async (configId: string) => ({
      configId,
      deviceId: 'greenhouse-01',
      status: 'APPLIED',
      reason: null,
      wasLate: false,
    }))
    const { result, unmount } = renderHook(() =>
      useGreenhouseDashboard({ deviceId: 'greenhouse-01', enabled: true }),
    )
    await waitFor(() => expect(result.current.status).toBe('ready'))
    await act(async () => { await result.current.publishConfig(fixtureDeviceConfig) })
    await act(async () => { await result.current.publishConfig(fixtureDeviceConfig) })
    await waitFor(() => expect(result.current.configAck).toMatchObject({
      configId: 'cfg-new',
      status: 'APPLIED',
    }))
    act(() => FakeWebSocket.instances[0].message({
      type: 'config_result',
      data: { configId: 'cfg-old', result: 'REJECTED', reason: 'OLD', wasLate: false },
    }))
    expect(result.current.configAck).toMatchObject({ configId: 'cfg-new', status: 'APPLIED' })
    expect(apiMocks.getConfigStatus).toHaveBeenCalledWith('cfg-new')
    unmount()
  })
})
