import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  mockDeviceState,
  mockNoWaterTelemetry,
  mockOfflineState,
  mockSensorFaultTelemetry,
  mockTelemetry,
  mockTelemetryHistoryByBucket,
} from '../../mocks/greenhouse'
import { OverviewPage } from './OverviewPage'

describe('OverviewPage', () => {
  it('hiển thị các chỉ số và trạng thái thực tế từ dữ liệu mới nhất', () => {
    render(
      <OverviewPage
        telemetry={mockTelemetry}
        deviceState={mockDeviceState}
        history={mockTelemetryHistoryByBucket}
        dataSource="mock"
      />,
    )

    expect(screen.getByRole('heading', { name: 'Theo dõi khí hậu' })).toBeInTheDocument()
    expect(screen.getByLabelText('Nhiệt độ: 28,6 °C')).toBeInTheDocument()
    expect(screen.getByLabelText('Độ ẩm không khí: 67,4 %')).toBeInTheDocument()
    expect(screen.getByLabelText('Nguồn nước: Đủ nước')).toBeInTheDocument()
    expect(screen.getByText('ĐANG BẬT')).toBeInTheDocument()
    expect(screen.getByText('Dữ liệu mô phỏng')).toBeInTheDocument()
  })

  it('không chuyển giá trị cảm biến null thành 0', () => {
    render(
      <OverviewPage
        telemetry={mockSensorFaultTelemetry}
        deviceState={mockDeviceState}
        history={mockTelemetryHistoryByBucket}
        dataSource="mock"
      />,
    )

    expect(screen.getByLabelText('Nhiệt độ: Không có dữ liệu')).toBeInTheDocument()
    expect(screen.getByLabelText('Nguồn nước: Không rõ')).toBeInTheDocument()
    expect(screen.getByText('Cảm biến nước không đáng tin cậy')).toBeInTheDocument()
  })

  it('phân biệt hết nước với lỗi cảm biến nước', () => {
    render(
      <OverviewPage
        telemetry={mockNoWaterTelemetry}
        deviceState={{ ...mockDeviceState, failsafeActive: true, mist: false }}
        history={mockTelemetryHistoryByBucket}
        dataSource="mock"
      />,
    )

    expect(screen.getByLabelText('Nguồn nước: Hết nước')).toBeInTheDocument()
    expect(screen.getByText('Bơm bị khóa bởi failsafe')).toBeInTheDocument()
    expect(screen.getByText('Đang can thiệp')).toBeInTheDocument()
  })

  it('hiển thị trạng thái offline do Backend cung cấp', () => {
    render(
      <OverviewPage
        telemetry={mockTelemetry}
        deviceState={mockOfflineState}
        history={mockTelemetryHistoryByBucket}
        dataSource="mock"
      />,
    )

    expect(screen.getAllByText('Ngoại tuyến')).not.toHaveLength(0)
    expect(screen.getByText('Mất kết nối')).toBeInTheDocument()
  })
})
