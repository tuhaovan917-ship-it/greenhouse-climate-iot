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
import type { ControlMode, DeviceConfig } from '../../types/api'
import { ControlPanel } from './ControlPanel'

function renderControlPanel(
  overrides: Partial<ComponentProps<typeof ControlPanel>> = {},
) {
  const onSendCommand = vi.fn().mockResolvedValue(undefined)
  const onPublishMode = vi.fn().mockImplementation(async (mode: ControlMode) => ({
    status: 'PUBLISHED' as const,
    config: { ...fixtureDeviceConfig, mode },
  }))
  const onPublishConfig = vi.fn().mockImplementation(async (config: DeviceConfig) => ({
    status: 'PUBLISHED' as const,
    config,
  }))

  render(
    <ControlPanel
      commands={fixtureCommandHistory}
      config={fixtureDeviceConfig}
      deviceState={fixtureDeviceState}
      onPublishConfig={onPublishConfig}
      onPublishMode={onPublishMode}
      onSendCommand={onSendCommand}
      telemetry={fixtureTelemetry}
      {...overrides}
    />,
  )

  return { onSendCommand, onPublishMode, onPublishConfig }
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

  it('phân biệt PUBLISHED với trạng thái mode thực tế', async () => {
    const user = userEvent.setup()
    const { onPublishMode } = renderControlPanel()

    await user.click(screen.getByRole('button', { name: 'Yêu cầu MANUAL' }))

    expect(onPublishMode).toHaveBeenCalledWith('MANUAL')
    expect(screen.getByText(/PUBLISHED chưa đồng nghĩa ESP32 đã áp dụng/i)).toBeInTheDocument()
    expect(screen.getByText(/Đang chờ trạng thái thực tế từ ESP32/i)).toBeInTheDocument()
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
    expect(screen.getByText(/Đã publish các ngưỡng mới/i)).toBeInTheDocument()
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
})
