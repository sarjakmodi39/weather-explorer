import { useState, type ChangeEvent, type FormEvent } from 'react'

import { storeWeatherData } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { validateInputs, type InputValues } from '../lib/transform'
import { StatusBanner } from './StatusBanner'

const PRESETS = [
  { label: 'Mumbai', latitude: '19.0760', longitude: '72.8777' },
  { label: 'London', latitude: '51.5072', longitude: '-0.1276' },
  { label: 'New York', latitude: '40.7128', longitude: '-74.0060' },
  { label: 'Sydney', latitude: '-33.8688', longitude: '151.2093' },
]

/** Default to a fully-available 7-day window: Open-Meteo's archive lags
 *  roughly two days, so we end three days back and stay clear of it. */
function defaultRange() {
  const end = new Date()
  end.setDate(end.getDate() - 3)
  const start = new Date(end)
  start.setDate(start.getDate() - 6)
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  return { startDate: iso(start), endDate: iso(end) }
}

const FIELD =
  'w-full rounded-md border border-slate-300 px-3 py-2 text-sm ' +
  'focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500'

export function InputPanel({ onStored }: { onStored: (filename: string) => void }) {
  const [values, setValues] = useState<InputValues>({
    latitude: '19.0760',
    longitude: '72.8777',
    ...defaultRange(),
  })
  const [localError, setLocalError] = useState<string | null>(null)
  const [storedFile, setStoredFile] = useState<string | null>(null)

  const store = useAsync(storeWeatherData)

  // Explicit type-only imports: `React.ChangeEvent` would rely on the UMD
  // global, which TypeScript rejects inside a module under the modern JSX
  // transform the Vite template configures.
  const set = (key: keyof InputValues) => (event: ChangeEvent<HTMLInputElement>) =>
    setValues((previous) => ({ ...previous, [key]: event.target.value }))

  async function submit(event: FormEvent) {
    event.preventDefault()
    setStoredFile(null)

    // Catch the obvious mistakes here so they cost no round trip.
    const problem = validateInputs(values)
    setLocalError(problem)
    if (problem) return

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

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-lg font-semibold text-slate-800">Fetch &amp; store</h2>

      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-600">Latitude</span>
            <input
              className={FIELD}
              value={values.latitude}
              onChange={set('latitude')}
              inputMode="decimal"
              placeholder="-90 to 90"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-600">Longitude</span>
            <input
              className={FIELD}
              value={values.longitude}
              onChange={set('longitude')}
              inputMode="decimal"
              placeholder="-180 to 180"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-600">Start date</span>
            <input className={FIELD} type="date" value={values.startDate} onChange={set('startDate')} />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-600">End date</span>
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
              className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 hover:bg-slate-100"
            >
              {preset.label}
            </button>
          ))}
        </div>

        <button
          type="submit"
          disabled={store.loading}
          className="w-full rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-400 sm:w-auto"
        >
          {store.loading ? 'Fetching…' : 'Fetch & store data'}
        </button>

        <p className="text-xs text-slate-500">Maximum range is 31 days.</p>

        {localError && <StatusBanner kind="error" message={localError} />}
        {store.error && <StatusBanner kind="error" message={store.error} />}
        {storedFile && <StatusBanner kind="success" message={`Stored as ${storedFile}`} />}
      </form>
    </section>
  )
}
