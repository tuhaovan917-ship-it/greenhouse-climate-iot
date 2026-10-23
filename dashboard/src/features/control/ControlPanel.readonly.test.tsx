import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { fixtureDeviceConfig, fixtureDeviceState, fixtureTelemetry } from '../../test/fixtures'
import { ControlPanel } from './ControlPanel'

describe('A5.2 Viewer UI restrictions', () => {
  it('disables controls and does not call command/config callbacks', () => {
    const onSendCommand = vi.fn()
    const onPublishConfig = vi.fn()
    const onPublishMode = vi.fn()
    const { container } = render(
      <ControlPanel
        readOnly
        config={fixtureDeviceConfig}
        commands={[]}
        deviceState={fixtureDeviceState}
        telemetry={fixtureTelemetry}
        onSendCommand={onSendCommand}
        onPublishConfig={onPublishConfig}
        onPublishMode={onPublishMode}
      />,
    )
    expect(screen.getByText(/Quyền Viewer: chỉ xem/)).toBeInTheDocument()
    expect(screen.getAllByRole('spinbutton').every((input) => (input as HTMLInputElement).disabled)).toBe(true)
    expect(screen.getByRole('button', { name: 'Publish ngưỡng mới' })).toBeDisabled()
    const form = container.querySelector('form')
    expect(form).not.toBeNull()
    fireEvent.submit(form!)
    expect(onSendCommand).not.toHaveBeenCalled()
    expect(onPublishConfig).not.toHaveBeenCalled()
    expect(onPublishMode).not.toHaveBeenCalled()
  })
})
