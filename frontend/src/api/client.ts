/** The only module that knows the backend exists.
 *  Every failure arrives as an ApiError carrying the backend's message. */

import type {
  StoreRequest,
  StoreResponse,
  StoredFileMeta,
  WeatherPayload,
} from '../types'

const BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')

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
    response = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
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
    body: JSON.stringify(payload),
  })
}

export function listWeatherFiles(): Promise<StoredFileMeta[]> {
  return request<{ files: StoredFileMeta[] }>('/list-weather-files').then((r) => r.files)
}

export function getWeatherFileContent(name: string): Promise<WeatherPayload> {
  return request<WeatherPayload>(`/weather-file-content/${encodeURIComponent(name)}`)
}
