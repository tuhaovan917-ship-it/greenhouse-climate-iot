import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginPreview } from './LoginPreview'
import { login, logout, me, type AuthResponse } from '../../api/authClient'

vi.mock('../../api/authClient', () => ({
  login: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
}))

const session: AuthResponse = {
  user: { id: 'demo', username: 'admin', email: 'admin@example.test', role: 'admin', isActive: true },
  csrfToken: 'internal-token-for-test-only',
}

beforeEach(() => {
  vi.mocked(me).mockReset().mockRejectedValue(new Error('Not signed in'))
  vi.mocked(login).mockReset().mockResolvedValue(session)
  vi.mocked(logout).mockReset().mockResolvedValue({ status: 'logged_out' })
})

describe('LoginPreview A5.1', () => {
  it('switches to authenticated preview and can logout', async () => {
    const user = userEvent.setup()
    render(<LoginPreview />)
    await screen.findByRole('heading', { name: /Chào mừng.*trở lại/s })
    await user.type(screen.getByLabelText('Tên đăng nhập hoặc email'), 'admin')
    await user.type(screen.getByLabelText('Mật khẩu'), 'demo-private-password')
    await user.click(screen.getByRole('button', { name: 'Đăng nhập hệ thống' }))
    expect(await screen.findByRole('heading', { name: 'Đã xác thực thành công.' })).toBeInTheDocument()
    expect(login).toHaveBeenCalledWith('admin', 'demo-private-password')
    await user.click(screen.getByRole('button', { name: 'Đăng xuất' }))
    await waitFor(() => expect(logout).toHaveBeenCalledWith(session.csrfToken))
    expect(await screen.findByRole('heading', { name: /Chào mừng.*trở lại/s })).toBeInTheDocument()
  })

  it('restores an existing authenticated session during preview', async () => {
    vi.mocked(me).mockResolvedValue(session)
    render(<LoginPreview />)
    expect(await screen.findByRole('heading', { name: 'Đã xác thực thành công.' })).toBeInTheDocument()
    expect(screen.getByText(/Vai trò:/)).toBeInTheDocument()
  })
})
