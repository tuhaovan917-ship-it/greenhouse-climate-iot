import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  fixtureDeviceState,
  fixtureNoWaterTelemetry,
  fixtureOfflineState,
  fixtureSensorFaultTelemetry,
  fixtureTelemetry,
  fixtureTelemetryHistoryByBucket,
} from '../../test/fixtures'
import { OverviewPage } from './OverviewPage'

describe('OverviewPage', () => {
  it('hiển thị các chỉ số và trạng thái thực tế từ dữ liệu mới nhất', () => {
    render(
      <OverviewPage
        telemetry={fixtureTelemetry}
        deviceState={fixtureDeviceState}
        history={fixtureTelemetryHistoryByBucket['5m']}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Theo dõi khí hậu' })).toBeInTheDocument()
    expect(screen.getByLabelText('Nhiệt độ: 28,6 °C')).toBeInTheDocument()
    expect(screen.getByLabelText('Độ ẩm không khí: 67,4 %')).toBeInTheDocument()
    expect(screen.getByLabelText('Nguồn nước: Đủ nước')).toBeInTheDocument()
    expect(screen.getByText('ĐANG BẬT')).toBeInTheDocument()
  })

  it('không chuyển giá trị cảm biến null thành 0', () => {
    render(
      <OverviewPage
        telemetry={fixtureSensorFaultTelemetry}
        deviceState={fixtureDeviceState}
        history={fixtureTelemetryHistoryByBucket['5m']}
      />,
    )

    expect(screen.getByLabelText('Nhiệt độ: Không có dữ liệu')).toBeInTheDocument()
    expect(screen.getByLabelText('Nguồn nước: Không rõ')).toBeInTheDocument()
    expect(screen.getByText('Cảm biến nước không đáng tin cậy')).toBeInTheDocument()
  })

  it('render trạng thái an toàn khi Backend chưa có telemetry', () => {
    render(
      <OverviewPage
        telemetry={null}
        deviceState={{ ...fixtureOfflineState, updatedAt: null }}
        history={fixtureTelemetryHistoryByBucket['5m']}
      />,
    )

    expect(screen.getByText('bản tin telemetry đầu tiên.')).toBeInTheDocument()
    expect(screen.getByLabelText('Nhiệt độ: Không có dữ liệu')).toBeInTheDocument()
    expect(screen.getByLabelText('Nguồn nước: Chưa có dữ liệu')).toBeInTheDocument()
    expect(screen.getAllByText('Chưa nhận được telemetry từ thiết bị')).toHaveLength(3)
  })

  it('phân biệt hết nước với lỗi cảm biến nước', () => {
    render(
      <OverviewPage
        telemetry={fixtureNoWaterTelemetry}
        deviceState={{ ...fixtureDeviceState, failsafeActive: true, mist: false }}
        history={fixtureTelemetryHistoryByBucket['5m']}
      />,
    )

    expect(screen.getByLabelText('Nguồn nước: Hết nước')).toBeInTheDocument()
    expect(screen.getByText('Bơm bị khóa bởi failsafe')).toBeInTheDocument()
    expect(screen.getByText('Đang can thiệp')).toBeInTheDocument()
  })

  it('hiển thị trạng thái offline do Backend cung cấp', () => {
    render(
      <OverviewPage
        telemetry={fixtureTelemetry}
        deviceState={fixtureOfflineState}
        history={fixtureTelemetryHistoryByBucket['5m']}
      />,
    )

    expect(screen.getAllByText('Ngoại tuyến')).not.toHaveLength(0)
    expect(screen.getByText('Mất kết nối')).toBeInTheDocument()
  })
})
