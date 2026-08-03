import { describe, expect, it } from 'vitest'

import {
  clampPage,
  dayRangeGeometry,
  formatCityLabel,
  pageCount,
  paginate,
  summarizeRows,
  toDailyRows,
  validateInputs,
  type DailyRow,
} from './transform'
import type { GeocodeResult, WeatherPayload } from '../types'

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

describe('summarizeRows', () => {
  const ROW = (date: string, tempMax: number | null, tempMin: number | null): DailyRow => ({
    date,
    tempMax,
    tempMin,
    feelsMax: null,
    feelsMin: null,
  })

  it('finds the warmest and coldest day and the average swing over normal data', () => {
    const rows = [ROW('2024-06-01', 30, 20), ROW('2024-06-02', 34, 22), ROW('2024-06-03', 28, 18)]

    const summary = summarizeRows(rows)

    expect(summary.warmest).toEqual({ value: 34, date: '2024-06-02' })
    expect(summary.coldest).toEqual({ value: 18, date: '2024-06-03' })
    // swings: 10, 12, 10 -> mean 32/3
    expect(summary.avgSwing).toBeCloseTo(32 / 3)
  })

  it('returns nulls for every figure when every reading is null', () => {
    const rows = [ROW('2024-06-01', null, null), ROW('2024-06-02', null, null)]

    expect(summarizeRows(rows)).toEqual({ warmest: null, coldest: null, avgSwing: null })
  })

  it('treats a single row as both the warmest and coldest day', () => {
    const rows = [ROW('2024-06-01', 30, 20)]

    const summary = summarizeRows(rows)

    expect(summary.warmest).toEqual({ value: 30, date: '2024-06-01' })
    expect(summary.coldest).toEqual({ value: 20, date: '2024-06-01' })
    expect(summary.avgSwing).toBe(10)
  })

  it('returns all nulls for an empty array', () => {
    expect(summarizeRows([])).toEqual({ warmest: null, coldest: null, avgSwing: null })
  })

  it('excludes a day from the swing average when only one of its readings is null', () => {
    const rows = [ROW('2024-06-01', 30, 20), ROW('2024-06-02', 34, null)]

    const summary = summarizeRows(rows)

    expect(summary.warmest).toEqual({ value: 34, date: '2024-06-02' })
    expect(summary.coldest).toEqual({ value: 20, date: '2024-06-01' })
    expect(summary.avgSwing).toBe(10)
  })
})

describe('dayRangeGeometry', () => {
  const ROW = (
    tempMin: number | null,
    tempMax: number | null,
    feelsMin: number | null,
    feelsMax: number | null,
  ): DailyRow => ({ date: '2024-06-01', tempMin, tempMax, feelsMin, feelsMax })

  it('positions all four readings along an axis spanning the full set, for normal data', () => {
    // axis = [19, 32] (feels-like sit just outside min/max here), span 13
    const geometry = dayRangeGeometry(ROW(20, 30, 19, 32))

    expect(geometry.feelsMinPct).toBeCloseTo(0)
    expect(geometry.minPct).toBeCloseTo(((20 - 19) / 13) * 100)
    expect(geometry.maxPct).toBeCloseTo(((30 - 19) / 13) * 100)
    expect(geometry.feelsMaxPct).toBeCloseTo(100)
  })

  it('places every point at the midpoint when min and max are equal and feels-like is absent', () => {
    const geometry = dayRangeGeometry(ROW(25, 25, null, null))

    expect(geometry.minPct).toBe(50)
    expect(geometry.maxPct).toBe(50)
    expect(geometry.feelsMinPct).toBeNull()
    expect(geometry.feelsMaxPct).toBeNull()
  })

  it('extends the axis to include feels-like readings that fall outside the min-max span', () => {
    // axis = [10, 40] driven entirely by the feels-like readings
    const geometry = dayRangeGeometry(ROW(20, 30, 10, 40))

    expect(geometry.feelsMinPct).toBe(0)
    expect(geometry.minPct).toBeCloseTo(((20 - 10) / 30) * 100)
    expect(geometry.maxPct).toBeCloseTo(((30 - 10) / 30) * 100)
    expect(geometry.feelsMaxPct).toBe(100)
  })

  it('returns all nulls when every reading is null', () => {
    expect(dayRangeGeometry(ROW(null, null, null, null))).toEqual({
      minPct: null,
      maxPct: null,
      feelsMinPct: null,
      feelsMaxPct: null,
    })
  })

  it('omits a reading from the axis and the result when only it is null', () => {
    const geometry = dayRangeGeometry(ROW(20, 30, null, 34))

    expect(geometry.feelsMinPct).toBeNull()
    // axis = [20, 34], span 14
    expect(geometry.minPct).toBe(0)
    expect(geometry.maxPct).toBeCloseTo((10 / 14) * 100)
    expect(geometry.feelsMaxPct).toBe(100)
  })
})

describe('formatCityLabel', () => {
  const MUMBAI: GeocodeResult = {
    name: 'Mumbai',
    admin1: 'Maharashtra',
    country: 'India',
    country_code: 'IN',
    latitude: 19.076,
    longitude: 72.8777,
  }

  it('joins name, admin1, and country when all are present', () => {
    expect(formatCityLabel(MUMBAI)).toBe('Mumbai, Maharashtra, India')
  })

  it('drops admin1 when it is null', () => {
    expect(formatCityLabel({ ...MUMBAI, admin1: null })).toBe('Mumbai, India')
  })

  it('drops country when it is null', () => {
    expect(formatCityLabel({ ...MUMBAI, country: null })).toBe('Mumbai, Maharashtra')
  })

  it('falls back to the bare name when both admin1 and country are null', () => {
    expect(formatCityLabel({ ...MUMBAI, admin1: null, country: null })).toBe('Mumbai')
  })
})
