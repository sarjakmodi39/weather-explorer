import { useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from 'react'

import { searchCities, storeWeatherData } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import {
  formatCityLabel,
  MAX_RANGE_DAYS,
  validateInputs,
  type InputValues,
} from '../lib/transform'
import type { GeocodeResult } from '../types'
import { StatusBanner } from './StatusBanner'

const PRESETS = [
  { label: 'Mumbai', latitude: '19.0760', longitude: '72.8777' },
  { label: 'London', latitude: '51.5072', longitude: '-0.1276' },
  { label: 'New York', latitude: '40.7128', longitude: '-74.0060' },
  { label: 'Sydney', latitude: '-33.8688', longitude: '151.2093' },
]

/** Ends today by product choice, spanning the 7 days back from it. Open-Meteo's
 *  ERA5 archive lags real time by roughly a day or two, so the most recent day
 *  or two of this window may come back with null readings while the archive
 *  catches up — the UI already renders that as gaps in the chart and `—` in
 *  the table, so no special-casing is needed here.
 *
 *  Built from local calendar components (not `toISOString()`, which converts
 *  to UTC and would shift "today" back a day for anyone west of UTC). */
function defaultRange() {
  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - 7)
  const formatDate = (d: Date) => {
    const year = d.getFullYear()
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const date = String(d.getDate()).padStart(2, '0')
    return `${year}-${month}-${date}`
  }
  return { startDate: formatDate(start), endDate: formatDate(end) }
}

const FIELD =
  'w-full rounded-md border border-[var(--axis-line)] bg-[var(--surface-card)] px-3 py-2 text-sm ' +
  'text-[var(--ink-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]'

export function InputPanel({ onStored }: { onStored: (filename: string) => void }) {
  const [values, setValues] = useState<InputValues>({
    latitude: '19.0760',
    longitude: '72.8777',
    ...defaultRange(),
  })
  const [localError, setLocalError] = useState<string | null>(null)
  const [storedFile, setStoredFile] = useState<string | null>(null)

  const [cityQuery, setCityQuery] = useState('')
  const [cityResults, setCityResults] = useState<GeocodeResult[] | null>(null)
  const [cityNoMatch, setCityNoMatch] = useState(false)
  // Tracks the exact query text that was last turned into applied
  // coordinates, so an edited-but-unsearched box can be flagged below —
  // otherwise a typed city that's never searched silently leaves whatever
  // coordinates were already in the fields to be submitted instead.
  const [appliedCityQuery, setAppliedCityQuery] = useState<string | null>(null)

  const store = useAsync(storeWeatherData)
  const citySearch = useAsync(searchCities)

  // Explicit type-only imports: `React.ChangeEvent` would rely on the UMD
  // global, which TypeScript rejects inside a module under the modern JSX
  // transform the Vite template configures.
  const set = (key: keyof InputValues) => (event: ChangeEvent<HTMLInputElement>) =>
    setValues((previous) => ({ ...previous, [key]: event.target.value }))

  // Clears any stale search feedback — the result list, the no-match flag,
  // and the search error — so it never lingers next to a fresh selection or
  // a query the user has since edited away from.
  function clearCityFeedback() {
    setCityResults(null)
    setCityNoMatch(false)
    citySearch.reset()
  }

  // Applies a chosen result's coordinates, formatted to the same 4 decimal
  // places the backend stores in the filename.
  function applyCity(result: GeocodeResult) {
    setValues((previous) => ({
      ...previous,
      latitude: result.latitude.toFixed(4),
      longitude: result.longitude.toFixed(4),
    }))
    setAppliedCityQuery(cityQuery)
    clearCityFeedback()
  }

  async function runCitySearch() {
    // Without this, a held Enter key (OS key-repeat) or rapid presses fire
    // overlapping searches; useAsync has no cancellation, so whichever
    // response resolves last would win regardless of which query is newest.
    if (citySearch.loading) return

    const query = cityQuery.trim()
    if (query.length < 2) return

    clearCityFeedback()

    const results = await citySearch.run(query)
    if (results === null) return // citySearch.error already carries the message

    if (results.length === 0) {
      setCityNoMatch(true)
    } else if (results.length === 1) {
      applyCity(results[0])
    } else {
      setCityResults(results)
    }
  }

  // A nested button inside this <form> defaults to type="submit", and
  // pressing Enter in a text field implicitly activates the form's submit
  // button whenever one is present — both would submit the outer form, so
  // both paths are guarded explicitly.
  function handleCityKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault()
      void runCitySearch()
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setStoredFile(null)

    // Catch the obvious mistakes here so they cost no round trip.
    const problem = validateInputs(values)
    setLocalError(problem)
    if (problem) {
      store.reset()
      return
    }

    const result = await store.run({
      latitude: Number(values.latitude),
      longitude: Number(values.longitude),
      start_date: values.startDate,
      end_date: values.endDate,
    })

    if (result) {
      setStoredFile(result.file)
      onStored(result.file)
    }
  }

  // True while the box holds text that hasn't been turned into applied
  // coordinates — the cue for the unapplied-city trap (type a city, never
  // press Search, hit Fetch & store, and silently get stale coordinates).
  const cityUnapplied =
    cityQuery.trim().length > 0 && cityQuery.trim() !== appliedCityQuery?.trim()

  const LABEL = 'mb-1 block text-sm font-medium text-[var(--ink-secondary)]'

  return (
    <section className="rounded-lg border border-[var(--grid-line)] bg-[var(--surface-card)] p-4 shadow-sm sm:p-5">
      <h2 className="mb-4 text-lg font-semibold text-[var(--ink-primary)]">Fetch &amp; store</h2>

      <form onSubmit={submit} className="space-y-3">
        <label className="block">
          <span className={LABEL}>Search for a city</span>
          <div className="flex flex-wrap gap-2">
            <input
              className={`${FIELD} min-w-0 flex-1`}
              value={cityQuery}
              onChange={(event) => {
                setCityQuery(event.target.value)
                // The previous results/message describe the old query, not
                // this one — an edited box must not leave a stale list of
                // still-clickable buttons for a city the user no longer typed.
                clearCityFeedback()
              }}
              onKeyDown={handleCityKeyDown}
              placeholder="e.g. Mumbai"
            />
            <button
              type="button"
              onClick={() => void runCitySearch()}
              disabled={citySearch.loading || cityQuery.trim().length < 2}
              className="btn-secondary shrink-0"
            >
              {citySearch.loading ? 'Searching…' : 'Search'}
            </button>
          </div>
        </label>

        {cityUnapplied && (
          <p className="text-xs text-[var(--ink-muted)]">
            &ldquo;{cityQuery.trim()}&rdquo; hasn&rsquo;t been applied — the coordinates below
            are what will be used. Press Search to look it up.
          </p>
        )}

        {cityResults && (
          <ul className="animate-fade-in-up space-y-1 rounded-md border border-[var(--grid-line)] bg-[var(--surface-page)] p-2">
            {cityResults.map((result, index) => (
              <li key={`${result.latitude},${result.longitude},${index}`}>
                <button
                  type="button"
                  onClick={() => applyCity(result)}
                  className="focus-ring w-full rounded-md px-2 py-1 text-left text-sm text-[var(--ink-secondary)]
                    transition-colors duration-150 hover:bg-[var(--surface-card)]"
                >
                  {formatCityLabel(result)}
                </button>
              </li>
            ))}
          </ul>
        )}

        {cityNoMatch && <StatusBanner kind="info" message="No cities found." />}
        {citySearch.error && <StatusBanner kind="error" message={citySearch.error} />}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block">
            <span className={LABEL}>Latitude</span>
            <input
              className={FIELD}
              value={values.latitude}
              onChange={set('latitude')}
              inputMode="decimal"
              placeholder="-90 to 90"
            />
          </label>
          <label className="block">
            <span className={LABEL}>Longitude</span>
            <input
              className={FIELD}
              value={values.longitude}
              onChange={set('longitude')}
              inputMode="decimal"
              placeholder="-180 to 180"
            />
          </label>
          <label className="block">
            <span className={LABEL}>Start date</span>
            <input className={FIELD} type="date" value={values.startDate} onChange={set('startDate')} />
          </label>
          <label className="block">
            <span className={LABEL}>End date</span>
            <input className={FIELD} type="date" value={values.endDate} onChange={set('endDate')} />
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() =>
                setValues((previous) => ({
                  ...previous,
                  latitude: preset.latitude,
                  longitude: preset.longitude,
                }))
              }
              className="btn-chip"
            >
              {preset.label}
            </button>
          ))}
        </div>

        <button
          type="submit"
          disabled={store.loading}
          className="btn-primary w-full sm:w-auto"
        >
          {store.loading ? 'Fetching…' : 'Fetch & store data'}
        </button>

        <p className="text-xs text-[var(--ink-muted)]">Maximum range is {MAX_RANGE_DAYS} days.</p>

        {localError && <StatusBanner kind="error" message={localError} />}
        {store.error && <StatusBanner kind="error" message={store.error} />}
        {storedFile && <StatusBanner kind="success" message={`Stored as ${storedFile}`} />}
      </form>
    </section>
  )
}
