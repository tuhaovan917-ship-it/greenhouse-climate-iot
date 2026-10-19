export function formatMeasurement(
  value: number | null,
  options: Intl.NumberFormatOptions = { maximumFractionDigits: 1 },
): string {
  if (value === null) {
    return 'Không có dữ liệu'
  }

  return new Intl.NumberFormat('vi-VN', options).format(value)
}

export function formatTimestamp(value: string | null): string {
  if (!value) {
    return 'Chưa có dữ liệu'
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return 'Thời gian không hợp lệ'
  }

  return new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date)
}
