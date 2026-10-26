import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./features/auth/SecureDashboard', () => ({
  SecureDashboard: () => <p>STRICT_AUTH_GATE</p>,
}))

vi.mock('./features/auth/LoginPreview', () => ({
  LoginPreview: () => <p>LEGACY_LOGIN_PREVIEW</p>,
}))

afterEach(() => {
  vi.unstubAllEnvs()
  window.history.replaceState(null, '', '/')
})

describe('A6.5 strict authentication routing', () => {
  it('prioritizes strict auth over login preview', () => {
    vi.stubEnv('VITE_AUTH_GATE_ENABLED', '1')
    window.history.replaceState(null, '', '/?preview=login')

    render(<App />)

    expect(screen.getByText('STRICT_AUTH_GATE')).toBeInTheDocument()
    expect(screen.queryByText('LEGACY_LOGIN_PREVIEW')).not.toBeInTheDocument()
  })

  it('preserves the login preview in legacy demo mode', () => {
    vi.stubEnv('VITE_AUTH_GATE_ENABLED', '0')
    window.history.replaceState(null, '', '/?preview=login')

    render(<App />)

    expect(screen.getByText('LEGACY_LOGIN_PREVIEW')).toBeInTheDocument()
    expect(screen.queryByText('STRICT_AUTH_GATE')).not.toBeInTheDocument()
  })
})
