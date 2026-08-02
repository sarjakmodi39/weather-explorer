import { describe, expect, it } from 'vitest'

import {
  clampPage,
  pageCount,
  paginate,
  toDailyRows,
  validateInputs,
} from './transform'
import type { WeatherPayload } from '../types'

const PAYLOAD: WeatherPayload = {
  daily: {
    time: ['2024-06-01', '2024-06-02', '2024-06-03'],
    temperature_2m_max: [34.4, 31.6, null],
    temperature_2m_min: [28.1, 27.0, 26.2],
    apparent_temperature_max: [40.2, 37.1, 36.0],
    apparent_temperature_min: [31.0, 30.2, 29.8],
  },
}

describe('toDailyRows', () => {
  it('zips the columnar payload into one row per day', () => {
    const rows = toDailyRows(PAYLOAD)

    expect(rows).toHaveLength(3)
    expect(rows[0]).toEqual({
      date: '2024-06-01',
      tempMax: 34.4,
      tempMin: 28.1,
      feelsMax: 40.2,
      feelsMin: 31.0,
    })
  })

  it('keeps rows that have null readings rather than dropping them', () => {
    const rows = toDailyRows(PAYLOAD)

    expect(rows).toHaveLength(3)
    expect(rows[2].tempMax).toBeNull()
    expect(rows[2].tempMin).toBe(26.2)
  })

  it('returns an empty array for a payload with no daily block', () => {
    expect(toDailyRows({})).toEqual([])
    expect(toDailyRows({ daily: { time: [] } })).toEqual([])
  })

  it('tolerates a missing variable array', () => {
    const rows = toDailyRows({ daily: { time: ['2024-06-01'] } })

    expect(rows[0].tempMax).toBeNull()
    expect(rows[0].feelsMin).toBeNull()
  })
})

describe('paginate', () => {
  const rows = Array.from({ length: 25 }, (_, i) => i)

  it('returns the first page', () => {
    expect(paginate(rows, 1, 10)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
  })

  it('returns a partial final page', () => {
    expect(paginate(rows, 3, 10)).toEqual([20, 21, 22, 23, 24])
  })

  it('returns nothing past the end', () => {
    expect(paginate(rows, 9, 10)).toEqual([])
  })

  it('handles an empty input', () => {
    expect(paginate([], 1, 10)).toEqual([])
  })

  it('returns nothing for page 0', () => {
    expect(paginate(rows, 0, 10)).toEqual([])
  })

  it('returns nothing for negative page numbers', () => {
    expect(paginate(rows, -1, 10)).toEqual([])
  })
})

describe('pageCount', () => {
  it.each([
    [0, 10, 1],
    [1, 10, 1],
    [10, 10, 1],
    [11, 10, 2],
    [25, 10, 3],
    [25, 50, 1],
  ])('pageCount(%i, %i) === %i', (total, size, expected) => {
    expect(pageCount(total, size)).toBe(expected)
  })
})

describe('clampPage', () => {
  it('pulls an out-of-range page back to the last page', () => {
    // Reproduces the real bug: viewing page 3 of 25 rows, then switching
    // page size to 50 leaves only 1 page.
    expect(clampPage(3, 25, 50)).toBe(1)
  })

  it('leaves a valid page alone', () => {
    expect(clampPage(2, 25, 10)).toBe(2)
  })

  it('never returns less than 1', () => {
    expect(clampPage(0, 0, 10)).toBe(1)
  })
})

describe('validateInputs', () => {
  const VALID = {
    latitude: '19.076',
    longitude: '72.8777',
    startDate: '2024-06-01',
    endDate: '2024-06-10',
  }

  it('accepts valid input', () => {
    expect(validateInputs(VALID)).toBeNull()
  })

  it.each([
    [{ latitude: '' }, 'Latitude'],
    [{ latitude: 'abc' }, 'Latitude'],
    [{ latitude: '91' }, 'Latitude'],
    [{ longitude: '181' }, 'Longitude'],
    [{ startDate: '' }, 'date'],
    [{ startDate: '2024-06-11' }, 'on or before'],
    [{ endDate: '2024-07-02' }, '31 days'],
  ])('rejects %o', (patch, fragment) => {
    const message = validateInputs({ ...VALID, ...patch })
    expect(message).toContain(fragment)
  })

  it('accepts exactly 31 inclusive days, matching the backend', () => {
    expect(
      validateInputs({ ...VALID, startDate: '2024-06-01', endDate: '2024-07-01' }),
    ).toBeNull()
  })

  it('rejects end date on the day after the injected "now"', () => {
    // now is 2024-06-15 00:00:00 UTC
    const now = new Date('2024-06-15')
    const message = validateInputs(
      { ...VALID, startDate: '2024-06-01', endDate: '2024-06-16' },
      now,
    )
    expect(message).toContain('future')
  })

  it('accepts end date on the same UTC calendar day as injected "now"', () => {
    // now is 2024-06-15 00:00:00 UTC; end is 2024-06-15
    const now = new Date('2024-06-15')
    const result = validateInputs(
      { ...VALID, startDate: '2024-06-01', endDate: '2024-06-15' },
      now,
    )
    expect(result).toBeNull()
  })

  it('accepts end date on the same UTC date when "now" is late in the day', () => {
    // now is 2024-06-15 23:59:59 UTC; end is 2024-06-15
    // This proves the comparison is calendar-date, not instant
    const now = new Date('2024-06-15T23:59:59Z')
    const result = validateInputs(
      { ...VALID, startDate: '2024-06-01', endDate: '2024-06-15' },
      now,
    )
    expect(result).toBeNull()
  })
})
