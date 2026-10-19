import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import {
  mockCommandHistory,
  mockDeviceConfig,
  mockDeviceState,
  mockNoWaterTelemetry,
  mockTelemetry,
} from '../../mocks/greenhouse'
import type { ControlMode } from '../../types/api'
import { ControlPanel } from './ControlPanel'

function renderControlPanel(
  overrides: Partial<ComponentProps<typeof ControlPanel>> = {},
) {
  const onSendCommand = vi.fn().mockResolvedValue(undefined)
  const onPublishMode = vi.fn().mockImplementation(async (mode: ControlMode) => ({
    status: 'PUBLISHED' as const,
    config: { ...mockDeviceConfig, mode },
  }))

  render(
    <ControlPanel
      commands={mockCommandHistory}
      config={mockDeviceConfig}
      deviceState={mockDeviceState}
      onPublishMode={onPublishMode}
      onSendCommand={onSendCommand}
      telemetry={mockTelemetry}
      {...overrides}
    />,
  )

  return { onSendCommand, onPublishMode }
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
    const manualState = { ...mockDeviceState, mode: 'MANUAL' as const }
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
      deviceState: { ...mockDeviceState, mode: 'MANUAL' },
      telemetry: mockNoWaterTelemetry,
    })

    expect(screen.getByRole('button', { name: 'Bật Bơm phun sương' })).toBeDisabled()
    expect(screen.getByText('Hết nước — failsafe khóa bơm')).toBeInTheDocument()
  })

  it('khóa yêu cầu bật bơm khi chưa có telemetry', () => {
    renderControlPanel({
      deviceState: { ...mockDeviceState, mode: 'MANUAL' },
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

  it('hiển thị lý do từ chối và đánh dấu phản hồi trễ', () => {
    renderControlPanel()

    expect(screen.getByText('Hết nước — bơm bị khóa an toàn', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Phản hồi trễ')).toBeInTheDocument()
  })
})
