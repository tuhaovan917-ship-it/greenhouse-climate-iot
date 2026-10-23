import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { LoginPage } from './LoginPage'

describe('Greenhouse LoginPage A5.1', () => {
  it('renders accessible Vietnamese labels and brand story', () => {
    render(<LoginPage onLogin={vi.fn().mockResolvedValue(undefined)} />)
    expect(screen.getByRole('heading', { name: /Chào mừng.*trở lại/s })).toBeInTheDocument()
    expect(screen.getByLabelText('Tên đăng nhập hoặc email')).toBeInTheDocument()
    expect(screen.getByLabelText('Mật khẩu')).toHaveAttribute('type', 'password')
    expect(screen.getByRole('img', { name: /Minh họa kỹ thuật nhà kính/ })).toBeInTheDocument()
    expect(screen.getByText(/Sơ đồ minh họa/)).toBeInTheDocument()
  })

  it('sends trimmed username and password only after valid submit', async () => {
    const onLogin = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(<LoginPage onLogin={onLogin} />)
    await user.type(screen.getByLabelText('Tên đăng nhập hoặc email'), '  admin  ')
    await user.type(screen.getByLabelText('Mật khẩu'), 'demo-private-password')
    await user.click(screen.getByRole('button', { name: 'Đăng nhập hệ thống' }))
    await waitFor(() => expect(onLogin).toHaveBeenCalledWith('admin', 'demo-private-password'))
  })

  it('supports show and hide password', async () => {
    const user = userEvent.setup()
    render(<LoginPage onLogin={vi.fn().mockResolvedValue(undefined)} />)
    const input = screen.getByLabelText('Mật khẩu')
    await user.click(screen.getByRole('button', { name: 'Hiện mật khẩu' }))
    expect(input).toHaveAttribute('type', 'text')
    await user.click(screen.getByRole('button', { name: 'Ẩn mật khẩu' }))
    expect(input).toHaveAttribute('type', 'password')
  })

  it('refuses empty credentials, shows server error without losing input', async () => {
    const onLogin = vi.fn().mockRejectedValue(new Error('Sai thông tin đăng nhập'))
    render(<LoginPage onLogin={onLogin} />)
    fireEvent.submit(screen.getByRole('button', { name: 'Đăng nhập hệ thống' }).closest('form')!)
    expect(screen.getByRole('alert')).toHaveTextContent('Vui lòng nhập tài khoản')
    expect(onLogin).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Tên đăng nhập hoặc email'), { target: { value: 'viewer' } })
    fireEvent.change(screen.getByLabelText('Mật khẩu'), { target: { value: 'demo-private-password' } })
    fireEvent.submit(screen.getByRole('button', { name: 'Đăng nhập hệ thống' }).closest('form')!)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Sai thông tin đăng nhập'))
    expect(screen.getByLabelText('Tên đăng nhập hoặc email')).toHaveValue('viewer')
  })
})
