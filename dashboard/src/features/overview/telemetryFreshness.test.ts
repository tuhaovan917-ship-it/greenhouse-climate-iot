import { describe, expect, it } from 'vitest'
import { fixtureTelemetry } from '../../test/fixtures'
import { isTelemetryStale } from './telemetryFreshness'

describe('isTelemetryStale', () => {
  it('chỉ đánh dấu dữ liệu cũ, không tự suy ra thiết bị offline', () => {
    const receivedAt = Date.parse(fixtureTelemetry.receivedAt)

    expect(isTelemetryStale(fixtureTelemetry, true, receivedAt + 9_000)).toBe(false)
    expect(isTelemetryStale(fixtureTelemetry, true, receivedAt + 11_000)).toBe(true)
    expect(isTelemetryStale(fixtureTelemetry, false, receivedAt + 11_000)).toBe(false)
  })
})
