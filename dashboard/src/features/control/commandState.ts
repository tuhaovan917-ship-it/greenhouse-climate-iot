import type {
  CommandAccepted,
  CommandActivity,
  CommandLog,
  CommandRequest,
  CommandResultData,
} from '../../types/api'

function isTerminal(command: CommandActivity) {
  return command.status !== 'PENDING'
}

function completionTime(command: CommandActivity) {
  return command.completedAt ? Date.parse(command.completedAt) : 0
}

function reconcileCommand(
  current: CommandActivity,
  incoming: CommandLog,
): CommandActivity {
  if (isTerminal(current) && incoming.status === 'PENDING') {
    return current
  }

  if (
    isTerminal(current) &&
    incoming.status !== 'PENDING' &&
    completionTime(current) > completionTime(incoming)
  ) {
    return current
  }

  return {
    ...incoming,
    wasLate:
      current.wasLate === true ||
      (current.status === 'TIMEOUT' &&
        (incoming.status === 'APPLIED' || incoming.status === 'REJECTED')),
  }
}

export function createPendingCommand(
  request: CommandRequest,
  accepted: CommandAccepted,
  requestedAt: string,
): CommandActivity {
  return {
    commandId: accepted.commandId,
    deviceId: request.deviceId,
    device: request.device,
    requestedOn: request.on,
    status: 'PENDING',
    reason: null,
    requestedAt,
    completedAt: null,
  }
}

export function mergeCommandResult(
  commands: CommandActivity[],
  result: CommandResultData,
  receivedAt: string,
): CommandActivity[] {
  let changed = false

  const nextCommands = commands.map((command) => {
    if (command.commandId !== result.commandId) {
      return command
    }

    const nextWasLate = result.wasLate === true || command.wasLate === true
    const nextReason = result.reason ?? null

    if (
      command.status === result.result &&
      (command.reason ?? null) === nextReason &&
      Boolean(command.wasLate) === nextWasLate
    ) {
      return command
    }

    changed = true
    return {
      ...command,
      status: result.result,
      reason: nextReason,
      completedAt: receivedAt,
      wasLate: nextWasLate,
    }
  })

  return changed ? nextCommands : commands
}

export function reconcileCommandSnapshot(
  commands: CommandActivity[],
  incoming: CommandLog[],
): CommandActivity[] {
  const currentById = new Map(
    commands.map((command) => [command.commandId, command]),
  )
  const reconciled = incoming.map((command) => {
    const current = currentById.get(command.commandId)
    currentById.delete(command.commandId)
    return current ? reconcileCommand(current, command) : command
  })

  return [...reconciled, ...currentById.values()].sort(
    (left, right) => Date.parse(right.requestedAt) - Date.parse(left.requestedAt),
  )
}
