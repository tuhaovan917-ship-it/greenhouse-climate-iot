/** A5.2: tab-local CSRF state only. Server session stays in an HttpOnly cookie. */
import type { AuthResponse } from './authClient'

export const SESSION_EXPIRED_EVENT = 'greenhouse:session-expired'

let activeAuth: AuthResponse | null = null

export function setActiveAuth(value: AuthResponse | null): void {
  activeAuth = value
}

export function getCsrfToken(): string | null {
  return activeAuth?.csrfToken ?? null
}

export function isSecureDashboardMode(): boolean {
  return import.meta.env.VITE_AUTH_GATE_ENABLED === '1' ||
    new URLSearchParams(window.location.search).get('preview') === 'secure'
}

export function expireActiveAuth(): void {
  if (!activeAuth) return
  activeAuth = null
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
}
