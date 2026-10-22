import { describe, expect, it } from 'vitest'
import { getHistoryBounds, normalizeHistoryQuery } from './historyQuery'

describe('historyQuery', () => {
  it('tạo khoảng [from, to) đúng theo UTC cho Backend', () => {
    const now = Date.parse('2026-10-19T12:00:00Z')

    expect(getHistoryBounds('6h', now)).toEqual({
      from: '2026-10-19T06:00:00.000Z',
      to: '2026-10-19T12:00:00.000Z',
    })
  })

  it('tự chọn bucket an toàn khi khoảng thời gian quá rộng cho raw', () => {
    expect(normalizeHistoryQuery({ bucket: 'raw', range: '24h' })).toEqual({
      bucket: '5m',
      range: '24h',
    })
    expect(normalizeHistoryQuery({ bucket: 'raw', range: '15m' })).toEqual({
      bucket: 'raw',
      range: '15m',
    })
  })
})
