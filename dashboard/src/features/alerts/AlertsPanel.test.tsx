import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { fixtureAlerts } from '../../test/fixtures'
import type { Alert } from '../../types/api'
import { AlertsPanel } from './AlertsPanel'

describe('AlertsPanel', () => {
  it('mặc định ưu tiên cảnh báo active và có empty state an toàn', () => {
    render(<AlertsPanel alerts={fixtureAlerts} />)

    expect(screen.getByRole('button', { name: 'Đang hoạt động (0)' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Không có cảnh báo đang hoạt động')).toBeInTheDocument()
  })

  it('hiển thị lại lịch sử đã xử lý sau reload', async () => {
    const user = userEvent.setup()
    render(<AlertsPanel alerts={fixtureAlerts} />)

    await user.click(screen.getByRole('button', { name: 'Đã xử lý (2)' }))

    expect(screen.getByText('Hết nước')).toBeInTheDocument()
    expect(screen.getByText('Mất kết nối')).toBeInTheDocument()
    expect(screen.getAllByText('Nghiêm trọng')).toHaveLength(2)
  })

  it('hiển thị severity và thời điểm gần nhất của cảnh báo active', () => {
    const activeAlert: Alert = {
      id: 99,
      deviceId: 'greenhouse-01',
      code: 'SENSOR_FAULT',
      severity: 'WARNING',
      message: 'Cảm biến mực nước không đáng tin cậy.',
      active: true,
      startedAt: '2026-10-19T10:00:00Z',
      lastSeenAt: '2026-10-19T10:00:10Z',
      resolvedAt: null,
    }

    render(<AlertsPanel alerts={[activeAlert]} />)

    expect(screen.getByText('Lỗi cảm biến')).toBeInTheDocument()
    expect(screen.getByText('Cảnh báo')).toBeInTheDocument()
    expect(screen.getByText('Gặp gần nhất')).toBeInTheDocument()
  })
})
