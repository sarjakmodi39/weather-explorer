/** The only module that knows the backend exists.
 *  Every failure arrives as an ApiError carrying the backend's message. */

import type {
  StoreRequest,
  StoreResponse,
  StoredFileMeta,
  WeatherPayload,
} from '../types'

const rawBase = import.meta.env.VITE_API_BASE

if (!rawBase) {
  // Without this, BASE silently becomes '', every request targets the
  // frontend's own origin, and the user sees a bare "Not Found" with no clue
  // that the build is missing its backend URL.
  console.warn(
    'VITE_API_BASE is not set at build time — API requests will target the ' +
      "frontend's own origin and almost certainly fail.",
  )
}

const BASE = (rawBase ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    // Content-Type is set per-call (only where there is a body) rather than
    // here for every request: it is not a CORS-safelisted header, so setting
    // it on GETs would force a needless preflight round trip on every one.
    response = await fetch(`${BASE}${path}`, init)
  } catch {
    // fetch only rejects on network-level failure, never on 4xx/5xx.
    throw new ApiError('Cannot reach the API. Is the backend running?', 0)
  }

  if (!response.ok) {
    // The backend guarantees {"status","message"} on every error.
    const message = await response
      .json()
      .then((body) => body?.message ?? response.statusText)
      .catch(() => response.statusText)
    throw new ApiError(message, response.status)
  }

  return response.json() as Promise<T>
}

export function storeWeatherData(payload: StoreRequest): Promise<StoreResponse> {
  return request<StoreResponse>('/store-weather-data', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listWeatherFiles(): Promise<StoredFileMeta[]> {
  return request<{ files: StoredFileMeta[] }>('/list-weather-files').then((r) => r.files)
}

export function getWeatherFileContent(name: string): Promise<WeatherPayload> {
  return request<WeatherPayload>(`/weather-file-content/${encodeURIComponent(name)}`)
}
