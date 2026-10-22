export const dashboardConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  wsUrl: import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws',
  apiKey: import.meta.env.VITE_API_KEY ?? '',
  deviceId: import.meta.env.VITE_DEVICE_ID ?? 'greenhouse-01',
} as const
