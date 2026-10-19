/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_WS_URL?: string
  readonly VITE_API_KEY?: string
  readonly VITE_DEVICE_ID?: string
  readonly VITE_DATA_SOURCE?: 'mock' | 'live'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
