import type {
  CommandAccepted,
  CommandActivity,
  CommandRequest,
  CommandResultData,
} from '../../types/api'

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
