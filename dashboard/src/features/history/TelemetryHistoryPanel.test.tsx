import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fixtureTelemetryHistoryByBucket } from '../../test/fixtures'
import { normalizeTelemetryHistory } from './historyTransform'
import { TelemetryHistoryPanel } from './TelemetryHistoryPanel'

function renderHistory(
  overrides: Partial<ComponentProps<typeof TelemetryHistoryPanel>> = {},
) {
  const onQueryChange = vi.fn()
  const onRetry = vi.fn()

  render(
    <TelemetryHistoryPanel
      error={null}
      history={fixtureTelemetryHistoryByBucket['5m']}
      loading={false}
      onQueryChange={onQueryChange}
      onRetry={onRetry}
      {...overrides}
    />,
  )

  return { onQueryChange, onRetry }
}

describe('TelemetryHistoryPanel', () => {
  it('sắp xếp dữ liệu Backend theo thời gian tăng dần và giữ nguyên null', () => {
    const points = normalizeTelemetryHistory({
      bucket: 'raw',
      data: [
        {
          ...fixtureTelemetryHistoryByBucket.raw.data[0],
          id: 2,
          receivedAt: '2026-10-19T09:00:00Z',
          temperatureC: null,
        },
        {
          ...fixtureTelemetryHistoryByBucket.raw.data[1],
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
    renderHistory()

    expect(screen.getByRole('heading', { name: 'Lịch sử môi trường' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Xem trung bình mỗi 5 phút' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByRole('img', { name: 'Biểu đồ nhiệt độ theo thời gian' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Biểu đồ độ ẩm theo thời gian' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Biểu đồ cường độ sáng theo thời gian' })).toBeInTheDocument()
  })

  it('gửi query Backend khi đổi khoảng thời gian và bucket', async () => {
    const user = userEvent.setup()
    const { onQueryChange } = renderHistory()

    expect(screen.getByRole('button', { name: 'Xem mẫu thô' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '15 phút' }))
    await user.click(screen.getByRole('button', { name: 'Xem mẫu thô' }))

    expect(screen.getByRole('button', { name: 'Xem mẫu thô' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(onQueryChange).toHaveBeenLastCalledWith({ bucket: 'raw', range: '15m' })
  })

  it('hiển thị empty state khi bucket được chọn không có dữ liệu', () => {
    renderHistory({ history: { bucket: '5m', data: [] } })

    expect(screen.getByText('Chưa có dữ liệu lịch sử')).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'Biểu đồ nhiệt độ theo thời gian' })).not.toBeInTheDocument()
  })

  it('hiển thị lỗi history riêng và cho phép thử lại', async () => {
    const user = userEvent.setup()
    const { onRetry } = renderHistory({
      error: 'Khoảng thời gian quá rộng',
      history: null,
    })

    expect(screen.getByRole('alert')).toHaveTextContent('Khoảng thời gian quá rộng')
    await user.click(screen.getByRole('button', { name: 'Thử tải lại' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
