/** Shapes exchanged with the backend. Mirrors backend/app/schemas.py. */

export interface StoredFileMeta {
  name: string
  size: number // bytes
  created_at: string // ISO 8601
}

/** The Open-Meteo archive response, stored verbatim.
 *  `daily` is columnar: parallel arrays indexed by day. */
export interface WeatherPayload {
  latitude?: number
  longitude?: number
  timezone?: string
  elevation?: number
  daily_units?: Record<string, string>
  daily?: {
    time: string[]
    temperature_2m_max?: (number | null)[]
    temperature_2m_min?: (number | null)[]
    apparent_temperature_max?: (number | null)[]
    apparent_temperature_min?: (number | null)[]
  }
}

export interface StoreRequest {
  latitude: number
  longitude: number
  start_date: string
  end_date: string
}

export interface StoreResponse {
  status: string
  file: string
}

/** One geocoding match. `admin1` and `country` are only ever missing for the
 *  handful of places Open-Meteo has no region/country data for. */
export interface GeocodeResult {
  name: string
  admin1: string | null
  country: string | null
  country_code: string | null
  latitude: number
  longitude: number
}

export interface GeocodeResponse {
  results: GeocodeResult[]
}
