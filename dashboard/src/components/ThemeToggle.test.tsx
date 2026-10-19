import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ThemeToggle } from './ThemeToggle'

describe('ThemeToggle', () => {
  it('chuyển qua lại giữa chế độ sáng và tối, đồng thời lưu lựa chọn', async () => {
    const user = userEvent.setup()
    render(<ThemeToggle />)

    const switchButton = screen.getByRole('switch', {
      name: 'Chuyển sang chế độ tối',
    })

    expect(switchButton).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText('Sáng')).toBeInTheDocument()
    expect(screen.getByTestId('theme-switch-track')).toHaveClass('shrink-0')
    expect(screen.getByTestId('theme-switch-thumb')).toHaveClass('left-0.5', 'translate-x-0')

    await user.click(switchButton)

    expect(document.documentElement).toHaveClass('dark')
    expect(window.localStorage.getItem('greenhouse-theme')).toBe('dark')
    expect(
      screen.getByRole('switch', { name: 'Chuyển sang chế độ sáng' }),
    ).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('Tối')).toBeInTheDocument()
    expect(screen.getByTestId('theme-switch-thumb')).toHaveClass('left-0.5', 'translate-x-4')

    await user.click(screen.getByRole('switch', { name: 'Chuyển sang chế độ sáng' }))

    expect(document.documentElement).not.toHaveClass('dark')
    expect(window.localStorage.getItem('greenhouse-theme')).toBe('light')
  })

  it('khôi phục chế độ tối đã lưu khi tải lại component', () => {
    window.localStorage.setItem('greenhouse-theme', 'dark')

    render(<ThemeToggle />)

    expect(document.documentElement).toHaveClass('dark')
    expect(
      screen.getByRole('switch', { name: 'Chuyển sang chế độ sáng' }),
    ).toHaveAttribute('aria-checked', 'true')
  })
})
