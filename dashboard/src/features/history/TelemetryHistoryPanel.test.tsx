import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { mockTelemetryHistoryByBucket } from '../../mocks/greenhouse'
import type { TelemetryHistoryByBucket } from '../../types/api'
import { normalizeTelemetryHistory } from './historyTransform'
import { TelemetryHistoryPanel } from './TelemetryHistoryPanel'

describe('TelemetryHistoryPanel', () => {
  it('sắp xếp dữ liệu Backend theo thời gian tăng dần và giữ nguyên null', () => {
    const points = normalizeTelemetryHistory({
      bucket: 'raw',
      data: [
        {
          ...mockTelemetryHistoryByBucket.raw.data[0],
          id: 2,
          receivedAt: '2026-10-19T09:00:00Z',
          temperatureC: null,
        },
        {
          ...mockTelemetryHistoryByBucket.raw.data[1],
          id: 1,
          receivedAt: '2026-10-19T08:59:00Z',
          temperatureC: 27.5,
        },
      ],
    })

    expect(points.map((point) => point.timestampMs)).toEqual([
      Date.parse('2026-10-19T08:59:00Z'),
      Date.parse('2026-10-19T09:00:00Z'),
    ])
    expect(points.at(-1)?.temperatureC).toBeNull()
  })

  it('mặc định hiển thị bucket 5 phút và ba biểu đồ môi trường', () => {
    render(<TelemetryHistoryPanel history={mockTelemetryHistoryByBucket} />)

    expect(screen.getByRole('heading', { name: 'Lịch sử môi trường' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Xem trung bình mỗi 5 phút' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByRole('img', { name: 'Biểu đồ nhiệt độ theo thời gian' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Biểu đồ độ ẩm theo thời gian' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Biểu đồ cường độ sáng theo thời gian' })).toBeInTheDocument()
  })

  it('cho phép chuyển sang dữ liệu raw mà không đổi null thành 0', async () => {
    const user = userEvent.setup()
    render(<TelemetryHistoryPanel history={mockTelemetryHistoryByBucket} />)

    await user.click(screen.getByRole('button', { name: 'Xem mẫu thô' }))

    expect(screen.getByRole('button', { name: 'Xem mẫu thô' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByText('Mẫu thô')).toBeInTheDocument()
    expect(screen.getByText(/không được đổi thành 0/i)).toBeInTheDocument()
  })

  it('hiển thị empty state khi bucket được chọn không có dữ liệu', () => {
    const emptyHistory: TelemetryHistoryByBucket = {
      ...mockTelemetryHistoryByBucket,
      '5m': { bucket: '5m', data: [] },
    }

    render(<TelemetryHistoryPanel history={emptyHistory} />)

    expect(screen.getByText('Chưa có dữ liệu lịch sử')).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'Biểu đồ nhiệt độ theo thời gian' })).not.toBeInTheDocument()
  })
})
