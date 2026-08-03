/** Pure functions only — no React, no fetch.
 *  Everything the chart and table render is derived from the loaded file
 *  through these, so there is never a second copy of the data to drift. */

import type { GeocodeResult, WeatherPayload } from '../types'

export interface DailyRow {
  date: string
  tempMax: number | null
  tempMin: number | null
  feelsMax: number | null
  feelsMin: number | null
}

/** Open-Meteo returns columnar arrays; the UI wants one object per day. */
export function toDailyRows(payload: WeatherPayload): DailyRow[] {
  const daily = payload.daily
  if (!daily?.time?.length) return []

  const at = (values: (number | null)[] | undefined, i: number): number | null =>
    values?.[i] ?? null

  return daily.time.map((date, i) => ({
    date,
    tempMax: at(daily.temperature_2m_max, i),
    tempMin: at(daily.temperature_2m_min, i),
    feelsMax: at(daily.apparent_temperature_max, i),
    feelsMin: at(daily.apparent_temperature_min, i),
  }))
}

export function paginate<T>(rows: T[], page: number, pageSize: number): T[] {
  if (page < 1) return []
  const start = (page - 1) * pageSize
  return rows.slice(start, start + pageSize)
}

/** Always at least 1, so the UI can render "Page 1 of 1" for an empty table. */
export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize))
}

/** Keeps the current page in range after the row count or page size changes. */
export function clampPage(page: number, total: number, pageSize: number): number {
  return Math.min(Math.max(1, page), pageCount(total, pageSize))
}

export interface InputValues {
  latitude: string
  longitude: string
  startDate: string
  endDate: string
}

export const MAX_RANGE_DAYS = 31
const MS_PER_DAY = 86_400_000

/** Mirrors backend/app/schemas.py so obvious mistakes cost no round trip.
 *  The server stays the authority — this is a convenience, not a guarantee. */
export function validateInputs(values: InputValues, now: Date = new Date()): string | null {
  const latitude = Number(values.latitude)
  const longitude = Number(values.longitude)

  if (values.latitude.trim() === '' || Number.isNaN(latitude)) {
    return 'Latitude must be a number.'
  }
  if (latitude < -90 || latitude > 90) {
    return 'Latitude must be between -90 and 90.'
  }
  if (values.longitude.trim() === '' || Number.isNaN(longitude)) {
    return 'Longitude must be a number.'
  }
  if (longitude < -180 || longitude > 180) {
    return 'Longitude must be between -180 and 180.'
  }
  if (!values.startDate || !values.endDate) {
    return 'Both a start date and an end date are required.'
  }

  const start = new Date(values.startDate)
  const end = new Date(values.endDate)
  if (Number.isNaN(start.valueOf()) || Number.isNaN(end.valueOf())) {
    return 'Dates must be valid calendar dates.'
  }
  if (start > end) {
    return 'Start date must be on or before end date.'
  }

  // Inclusive day count, matching the backend's rule exactly.
  const days = Math.round((end.valueOf() - start.valueOf()) / MS_PER_DAY) + 1
  if (days > MAX_RANGE_DAYS) {
    return `Date range must not exceed ${MAX_RANGE_DAYS} days (requested ${days}).`
  }

  // Compare UTC calendar dates, not instants. Mirror backend's UTC evaluation.
  const endDateString = end.toISOString().split('T')[0]
  const todayString = now.toISOString().split('T')[0]
  if (endDateString > todayString) {
    return 'End date must not be in the future.'
  }

  return null
}

/** Builds a human label from whichever of name/admin1/country exist, e.g.
 *  "Mumbai, Maharashtra, India", degrading to "Mumbai, India" or "Mumbai"
 *  when a part is null — never a trailing or doubled comma. */
export function formatCityLabel(result: GeocodeResult): string {
  return [result.name, result.admin1, result.country].filter(Boolean).join(', ')
}
