import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import {
  fixtureCommandHistory,
  fixtureDeviceConfig,
  fixtureDeviceState,
  fixtureNoWaterTelemetry,
  fixtureTelemetry,
} from '../../test/fixtures'
import type { ConfigAckStatus, ControlMode, DeviceConfig } from '../../types/api'
import { ControlPanel } from './ControlPanel'

function renderControlPanel(
  overrides: Partial<ComponentProps<typeof ControlPanel>> = {},
) {
  const onSendCommand = vi.fn().mockResolvedValue(undefined)
  const onPublishMode = vi.fn().mockImplementation(async (mode: ControlMode) => ({
    configId: 'cfg-ui-001',
    status: 'PENDING' as const,
    config: { ...fixtureDeviceConfig, mode },
  }))
  const onPublishConfig = vi.fn().mockImplementation(async (config: DeviceConfig) => ({
    configId: 'cfg-ui-001',
    status: 'PENDING' as const,
    config,
  }))

  const view = render(
    <ControlPanel
      commands={fixtureCommandHistory}
      config={fixtureDeviceConfig}
      configAck={null}
      deviceState={fixtureDeviceState}
      onPublishConfig={onPublishConfig}
      onPublishMode={onPublishMode}
      onSendCommand={onSendCommand}
      telemetry={fixtureTelemetry}
      {...overrides}
    />,
  )

  return { ...view, onSendCommand, onPublishMode, onPublishConfig }
}

describe('ControlPanel', () => {
  it('khóa điều khiển trực tiếp khi thiết bị đang ở AUTO', () => {
    renderControlPanel()

    expect(screen.getByRole('button', { name: 'Tắt Quạt thông gió' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Bật Bơm phun sương' })).toBeDisabled()
    expect(screen.getAllByText('Chỉ điều khiển trực tiếp trong chế độ MANUAL')).toHaveLength(3)
  })

  it('gửi đúng desired state trong MANUAL nhưng không tự đổi actual state', async () => {
    const user = userEvent.setup()
    const manualState = { ...fixtureDeviceState, mode: 'MANUAL' as const }
    const { onSendCommand } = renderControlPanel({ deviceState: manualState })

    await user.click(screen.getByRole('button', { name: 'Tắt Quạt thông gió' }))

    expect(onSendCommand).toHaveBeenCalledWith({
      deviceId: 'greenhouse-01',
      device: 'fan',
      on: false,
    })
    expect(screen.getByText('Đang bật')).toBeInTheDocument()
  })

  it('khóa yêu cầu bật bơm khi hết nước', () => {
    renderControlPanel({
      deviceState: { ...fixtureDeviceState, mode: 'MANUAL' },
      telemetry: fixtureNoWaterTelemetry,
    })

    expect(screen.getByRole('button', { name: 'Bật Bơm phun sương' })).toBeDisabled()
    expect(screen.getByText('Hết nước — failsafe khóa bơm')).toBeInTheDocument()
  })

  it('khóa yêu cầu bật bơm khi chưa có telemetry', () => {
    renderControlPanel({
      deviceState: { ...fixtureDeviceState, mode: 'MANUAL' },
      telemetry: null,
    })

    expect(screen.getByRole('button', { name: 'Bật Bơm phun sương' })).toBeDisabled()
    expect(screen.getByText('Chưa có dữ liệu nguồn nước — bơm bị khóa an toàn')).toBeInTheDocument()
  })

  it('publish mode nhưng giữ nguyên mode thực tế cho đến khi state của ESP32 cập nhật', async () => {
    const user = userEvent.setup()
    const { onPublishMode } = renderControlPanel()

    await user.click(screen.getByRole('button', { name: 'Yêu cầu MANUAL' }))

    expect(onPublishMode).toHaveBeenCalledWith('MANUAL')
    expect(screen.getByText('AUTO')).toBeInTheDocument()
    expect(screen.queryByText(/ESP32 đã áp dụng cấu hình/i)).not.toBeInTheDocument()
  })

  it('validate và publish đầy đủ cấu hình ngưỡng', async () => {
    const user = userEvent.setup()
    const { onPublishConfig } = renderControlPanel()

    const tempOnInput = screen.getByLabelText('Bật quạt khi nhiệt độ')
    await user.clear(tempOnInput)
    await user.type(tempOnInput, '31')
    await user.click(screen.getByRole('button', { name: 'Publish ngưỡng mới' }))

    expect(onPublishConfig).toHaveBeenCalledWith({
      ...fixtureDeviceConfig,
      tempOnC: 31,
    })
    expect(screen.queryByTestId('config-ack-status')).not.toBeInTheDocument()
  })

  it('không publish khi cặp ngưỡng hysteresis không hợp lệ', async () => {
    const user = userEvent.setup()
    const { onPublishConfig } = renderControlPanel()

    const tempOnInput = screen.getByLabelText('Bật quạt khi nhiệt độ')
    await user.clear(tempOnInput)
    await user.type(tempOnInput, '27')
    await user.click(screen.getByRole('button', { name: 'Publish ngưỡng mới' }))

    expect(onPublishConfig).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Ngưỡng bật quạt phải lớn hơn ngưỡng tắt quạt.',
    )
  })

  it('hiển thị lý do từ chối và đánh dấu phản hồi trễ', () => {
    renderControlPanel()

    expect(screen.getByText('Hết nước — bơm bị khóa an toàn', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Phản hồi trễ')).toBeInTheDocument()
  })

  it('hiển thị Config ACK PENDING/APPLIED/REJECTED/TIMEOUT và phản hồi trễ', () => {
    const states: Array<[ConfigAckStatus, string]> = [
      [{ configId: 'cfg-pending', deviceId: 'greenhouse-01', status: 'PENDING', wasLate: false }, 'Đang chờ ESP32 xác nhận cấu hình'],
      [{ configId: 'cfg-applied', deviceId: 'greenhouse-01', status: 'APPLIED', wasLate: false }, 'ESP32 đã áp dụng cấu hình.'],
      [{ configId: 'cfg-rejected', deviceId: 'greenhouse-01', status: 'REJECTED', reason: 'NVS_WRITE_FAILED', wasLate: false }, 'ESP32 không lưu được cấu hình vào bộ nhớ.'],
      [{ configId: 'cfg-timeout', deviceId: 'greenhouse-01', status: 'TIMEOUT', reason: 'TIMEOUT', wasLate: false }, 'Quá thời gian chờ ESP32 xác nhận cấu hình.'],
      [{ configId: 'cfg-late', deviceId: 'greenhouse-01', status: 'APPLIED', wasLate: true }, 'Phản hồi đến sau khi Backend đã timeout.'],
      [{ configId: 'cfg-late-rejected', deviceId: 'greenhouse-01', status: 'REJECTED', reason: 'NVS_WRITE_FAILED', wasLate: true }, 'ESP32 không lưu được cấu hình vào bộ nhớ.'],
    ]

    states.forEach(([configAck, message]) => {
      const { unmount } = render(
        <ControlPanel
          config={fixtureDeviceConfig}
          configAck={configAck}
          commands={[]}
          deviceState={fixtureDeviceState}
          telemetry={fixtureTelemetry}
          onSendCommand={vi.fn().mockResolvedValue(undefined)}
          onPublishConfig={vi.fn().mockResolvedValue({ configId: 'cfg-next', status: 'PENDING', config: fixtureDeviceConfig })}
          onPublishMode={vi.fn().mockResolvedValue({ configId: 'cfg-next', status: 'PENDING', config: fixtureDeviceConfig })}
        />,
      )
      expect(screen.getByText(new RegExp(message, 'i'))).toBeInTheDocument()
      if (configAck.wasLate) {
        expect(screen.getByText('Phản hồi trễ')).toBeInTheDocument()
      }
      unmount()
    })
  })

  it('giữ raw reason lạ và vô hiệu hóa publish trong khi Config PENDING', async () => {
    const user = userEvent.setup()
    const { onPublishConfig, onPublishMode } = renderControlPanel({
      configAck: {
        configId: 'cfg-pending',
        deviceId: 'greenhouse-01',
        status: 'PENDING',
        wasLate: false,
      },
      deviceState: { ...fixtureDeviceState, mode: 'MANUAL' },
    })

    expect(screen.getByRole('button', { name: 'Đang chờ ESP32' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Publish ngưỡng mới' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Đang chờ ESP32' }))
    expect(onPublishMode).not.toHaveBeenCalled()
    expect(onPublishConfig).not.toHaveBeenCalled()

    const { unmount } = render(
      <ControlPanel
        config={fixtureDeviceConfig}
        configAck={{ configId: 'cfg-unknown', deviceId: 'greenhouse-01', status: 'REJECTED', reason: 'FUTURE_REASON', wasLate: false }}
        commands={[]}
        deviceState={fixtureDeviceState}
        telemetry={fixtureTelemetry}
        onSendCommand={vi.fn().mockResolvedValue(undefined)}
        onPublishConfig={vi.fn().mockResolvedValue({ configId: 'cfg-next', status: 'PENDING', config: fixtureDeviceConfig })}
        onPublishMode={vi.fn().mockResolvedValue({ configId: 'cfg-next', status: 'PENDING', config: fixtureDeviceConfig })}
      />,
    )
    expect(screen.getByText(/FUTURE_REASON/)).toBeInTheDocument()
    unmount()
  })

  it('cho phép retry mode sau REJECTED hoặc TIMEOUT dù desired mode khác actual mode', () => {
    for (const status of ['REJECTED', 'TIMEOUT'] as const) {
      const { unmount } = renderControlPanel({
        config: { ...fixtureDeviceConfig, mode: 'MANUAL' },
        deviceState: { ...fixtureDeviceState, mode: 'AUTO' },
        configAck: { configId: `cfg-${status}`, deviceId: 'greenhouse-01', status, wasLate: false },
      })
      expect(screen.getByRole('button', { name: 'Xác nhận giữ AUTO' })).toBeEnabled()
      unmount()
    }
  })
  
  it('cho phép xác nhận giữ AUTO sau khi mất mạng', async () => {
    const user = userEvent.setup()

    const { onPublishMode } = renderControlPanel({
      config: {
        ...fixtureDeviceConfig,
        mode: 'MANUAL',
      },
      deviceState: {
        ...fixtureDeviceState,
        mode: 'AUTO',
        online: true,
      },
    })

    const button = screen.getByRole('button', {
      name: 'Xác nhận giữ AUTO',
    })

    expect(button).toBeEnabled()

    await user.click(button)

    expect(onPublishMode).toHaveBeenCalledTimes(1)
    expect(onPublishMode).toHaveBeenCalledWith('AUTO')
  })
})
