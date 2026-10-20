import { describe, expect, it } from 'vitest'
import type { CommandActivity } from '../../types/api'
import {
  createPendingCommand,
  mergeCommandResult,
  reconcileCommandSnapshot,
} from './commandState'

const pendingCommand: CommandActivity = {
  commandId: 'cmd-1',
  deviceId: 'greenhouse-01',
  device: 'fan',
  requestedOn: true,
  status: 'PENDING',
  reason: null,
  requestedAt: '2026-10-19T10:00:00Z',
  completedAt: null,
}

describe('commandState', () => {
  it('tạo log PENDING từ response 202 mà không giả lập trạng thái thiết bị', () => {
    const command = createPendingCommand(
      { deviceId: 'greenhouse-01', device: 'mist', on: true },
      { commandId: 'cmd-new', status: 'PENDING' },
      '2026-10-19T10:01:00Z',
    )

    expect(command).toMatchObject({
      commandId: 'cmd-new',
      device: 'mist',
      requestedOn: true,
      status: 'PENDING',
      completedAt: null,
    })
  })

  it('cho phép phản hồi trễ ghi đè TIMEOUT bằng kết quả thực tế', () => {
    const timedOut: CommandActivity = {
      ...pendingCommand,
      status: 'TIMEOUT',
      completedAt: '2026-10-19T10:00:05Z',
    }

    const updated = mergeCommandResult(
      [timedOut],
      {
        commandId: timedOut.commandId,
        result: 'APPLIED',
        wasLate: true,
      },
      '2026-10-19T10:00:07Z',
    )

    expect(updated[0]).toMatchObject({
      status: 'APPLIED',
      completedAt: '2026-10-19T10:00:07Z',
      wasLate: true,
    })
  })

  it('coi message QoS 1 trùng kết quả là no-op', () => {
    const applied: CommandActivity = {
      ...pendingCommand,
      status: 'APPLIED',
      completedAt: '2026-10-19T10:00:01Z',
    }

    const commands = [applied]
    const unchanged = mergeCommandResult(
      commands,
      { commandId: applied.commandId, result: 'APPLIED', wasLate: false },
      '2026-10-19T10:00:02Z',
    )

    expect(unchanged).toBe(commands)
    expect(unchanged[0].completedAt).toBe('2026-10-19T10:00:01Z')
  })

  it('đồng bộ PENDING thành kết quả cuối từ REST', () => {
    const updated = reconcileCommandSnapshot([pendingCommand], [
      {
        ...pendingCommand,
        status: 'APPLIED',
        completedAt: '2026-10-19T10:00:02Z',
      },
    ])

    expect(updated[0]).toMatchObject({
      commandId: pendingCommand.commandId,
      status: 'APPLIED',
      completedAt: '2026-10-19T10:00:02Z',
    })
  })

  it('không để REST PENDING cũ ghi đè kết quả WebSocket', () => {
    const applied: CommandActivity = {
      ...pendingCommand,
      status: 'APPLIED',
      completedAt: '2026-10-19T10:00:02Z',
    }

    const updated = reconcileCommandSnapshot([applied], [pendingCommand])

    expect(updated[0]).toBe(applied)
  })

  it('nhận biết phản hồi thực tế đến sau TIMEOUT khi đồng bộ REST', () => {
    const timedOut: CommandActivity = {
      ...pendingCommand,
      status: 'TIMEOUT',
      completedAt: '2026-10-19T10:00:05Z',
    }

    const updated = reconcileCommandSnapshot([timedOut], [
      {
        ...pendingCommand,
        status: 'REJECTED',
        reason: 'NO_WATER',
        completedAt: '2026-10-19T10:00:07Z',
      },
    ])

    expect(updated[0]).toMatchObject({
      status: 'REJECTED',
      reason: 'NO_WATER',
      wasLate: true,
    })
  })
})
