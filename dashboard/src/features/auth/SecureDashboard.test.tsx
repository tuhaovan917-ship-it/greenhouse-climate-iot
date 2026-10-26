import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthApiError, login, logout, me, type AuthResponse, type AuthUser } from '../../api/authClient'
import { getCsrfToken, setActiveAuth, SESSION_EXPIRED_EVENT } from '../../api/authSession'
import { SecureDashboard } from './SecureDashboard'

vi.mock('../../api/authClient', async (importOriginal) => {
  const module = await importOriginal<typeof import('../../api/authClient')>()
  return { ...module, login: vi.fn(), logout: vi.fn(), me: vi.fn() }
})

const admin: AuthResponse = {
  user: { id: 'admin-1', username: 'admin_a52', email: 'admin@example.test', role: 'admin', isActive: true },
  csrfToken: 'test-csrf-should-never-persist',
}
const viewer: AuthResponse = {
  user: { id: 'viewer-1', username: 'viewer_a52', email: 'viewer@example.test', role: 'viewer', isActive: true },
  csrfToken: 'viewer-csrf-for-test',
}

beforeEach(() => {
  setActiveAuth(null)
  vi.mocked(me).mockReset().mockRejectedValue(new AuthApiError(401, 'Unauthorized'))
  vi.mocked(login).mockReset().mockResolvedValue(admin)
  vi.mocked(logout).mockReset().mockResolvedValue({ status: 'logged_out' })
})

afterEach(() => setActiveAuth(null))

describe('A5.2 secure dashboard gate', () => {
  it('blocks mounting dashboard before /me verifies user', async () => {
    let resolve!: (session: AuthResponse) => void
    vi.mocked(me).mockReturnValue(new Promise<AuthResponse>((r) => { resolve = r }))
    const content = vi.fn((user: AuthUser) => <h1>Dashboard {user.username}</h1>)
    render(<SecureDashboard renderDashboard={content} />)
    expect(screen.getByText('Đang kiểm tra quyền truy cập…')).toBeInTheDocument()
    expect(content).not.toHaveBeenCalled()
    await act(async () => resolve(admin))
    expect(await screen.findByRole('heading', { name: 'Dashboard admin_a52' })).toBeInTheDocument()
    expect(getCsrfToken()).toBe(admin.csrfToken)
  })

  it('shows login on 401 and mounts dashboard only after successful login', async () => {
    const user = userEvent.setup()
    const content = vi.fn((account: AuthUser) => <h1>Dashboard {account.username}</h1>)
    render(<SecureDashboard renderDashboard={content} />)
    await screen.findByRole('heading', { name: /Chào mừng.*trở lại/s })
    expect(content).not.toHaveBeenCalled()
    await user.type(screen.getByLabelText('Tên đăng nhập hoặc email'), 'admin_a52')
    await user.type(screen.getByLabelText('Mật khẩu'), 'secret-strong-test-password')
    await user.click(screen.getByRole('button', { name: 'Đăng nhập hệ thống' }))
    expect(await screen.findByRole('heading', { name: 'Dashboard admin_a52' })).toBeInTheDocument()
    expect(login).toHaveBeenCalledWith('admin_a52', 'secret-strong-test-password')
  })

  it('supports viewer role and shows read-only notice', async () => {
    vi.mocked(me).mockResolvedValue(viewer)
    const content = vi.fn((account: AuthUser) => <p>Role {account.role}</p>)
    render(<SecureDashboard renderDashboard={content} />)
    expect(await screen.findByText('Role viewer')).toBeInTheDocument()
    expect(screen.getByText(/Chế độ chỉ xem/)).toBeInTheDocument()
    expect(content).toHaveBeenCalledWith(viewer.user)
  })

  it('revokes session on logout and unmounts dashboard', async () => {
    vi.mocked(me).mockResolvedValue(admin)
    const user = userEvent.setup()
    render(<SecureDashboard renderDashboard={() => <h1>Protected Overview</h1>} />)
    expect(await screen.findByRole('heading', { name: 'Protected Overview' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Đăng xuất' }))
    await waitFor(() => expect(logout).toHaveBeenCalledWith(admin.csrfToken))
    expect(await screen.findByRole('heading', { name: /Chào mừng.*trở lại/s })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Protected Overview' })).not.toBeInTheDocument()
    expect(getCsrfToken()).toBeNull()
  })

  it('removes protected dashboard immediately when REST signals 401', async () => {
    vi.mocked(me).mockResolvedValue(admin)
    render(<SecureDashboard renderDashboard={() => <h1>Protected Overview</h1>} />)
    expect(await screen.findByRole('heading', { name: 'Protected Overview' })).toBeInTheDocument()
    act(() => { window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT)) })
    expect(screen.getByRole('heading', { name: /Chào mừng.*trở lại/s })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Protected Overview' })).not.toBeInTheDocument()
  })

  it('does not pretend Backend network failure means anonymous', async () => {
    vi.mocked(me).mockRejectedValue(new TypeError('Failed to fetch'))
    render(<SecureDashboard renderDashboard={() => <h1>Protected Overview</h1>} />)
    expect(await screen.findByRole('heading', { name: 'Không kiểm tra được phiên đăng nhập' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Failed to fetch')
    expect(screen.queryByRole('heading', { name: /Chào mừng.*trở lại/s })).not.toBeInTheDocument()
  })
})
