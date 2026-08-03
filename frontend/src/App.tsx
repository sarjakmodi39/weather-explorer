import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { getWeatherFileContent, listWeatherFiles } from './api/client'
import { DataTable } from './components/DataTable'
import { FileList } from './components/FileList'
import { InputPanel } from './components/InputPanel'
import { StatusBanner } from './components/StatusBanner'
import { TempChart } from './components/TempChart'
import { useAsync } from './hooks/useAsync'
import { toDailyRows } from './lib/transform'
import type { StoredFileMeta, WeatherPayload } from './types'

export default function App() {
  const [files, setFiles] = useState<StoredFileMeta[]>([])
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [payload, setPayload] = useState<WeatherPayload | null>(null)

  // Loaded files are cached by name, so re-clicking one costs no request.
  const cache = useRef(new Map<string, WeatherPayload>())

  // Guards against a stale response committing over a newer selection: bumped
  // on every selectFile call, and checked after the await resolves. If a
  // newer selection has started by then, this one's result is discarded.
  const selectionToken = useRef(0)

  const {
    run: runListing,
    loading: listLoading,
    error: listError,
  } = useAsync(listWeatherFiles)
  const {
    run: runContent,
    loading: contentLoading,
    error: contentError,
  } = useAsync(getWeatherFileContent)

  // `run` is referentially stable (useCallback over a module-level import),
  // so this memoization is real and the effect's dependency array is honest.
  const refreshFiles = useCallback(async () => {
    const result = await runListing()
    if (result) setFiles(result)
  }, [runListing])

  useEffect(() => {
    void refreshFiles()
  }, [refreshFiles])

  const selectFile = useCallback(
    async (name: string) => {
      setSelectedName(name)

      const cached = cache.current.get(name)
      if (cached) {
        setPayload(cached)
        return
      }

      const token = ++selectionToken.current
      const result = await runContent(name)

      // Cache whatever came back — the data is still valid for this
      // filename even if a newer selection has since superseded it.
      if (result) {
        cache.current.set(name, result)
      }

      // A newer selection started while this one was in flight; let it win
      // and leave the current state alone.
      if (token !== selectionToken.current) return

      setPayload(result ?? null)
    },
    [runContent],
  )

  // Chart and table are derived from the loaded payload — never a second copy.
  const rows = useMemo(() => (payload ? toDailyRows(payload) : []), [payload])

  const selectedMeta = files.find((file) => file.name === selectedName)

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6">
          <h1 className="text-xl font-bold text-slate-800 sm:text-2xl">Weather Explorer</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Historical daily weather from Open-Meteo, stored in cloud object storage.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[22rem_1fr]">
          <div className="space-y-6">
            <InputPanel
              onStored={(name) => {
                void refreshFiles().then(() => selectFile(name))
              }}
            />
            <FileList
              files={files}
              loading={listLoading}
              error={listError}
              selectedName={selectedName}
              onSelect={(name) => void selectFile(name)}
              onRefresh={() => void refreshFiles()}
            />
          </div>

          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-lg font-semibold text-slate-800">Visualization</h2>

            {contentError && <StatusBanner kind="error" message={contentError} />}

            {contentLoading && (
              <p className="py-12 text-center text-sm text-slate-500">Loading file…</p>
            )}

            {!contentLoading && !payload && !contentError && (
              <StatusBanner
                kind="info"
                message="Select a stored file to see its chart and table."
              />
            )}

            {!contentLoading && payload && (
              <div className="space-y-5">
                <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                  <Metadata label="Latitude" value={payload.latitude?.toFixed(4) ?? '—'} />
                  <Metadata label="Longitude" value={payload.longitude?.toFixed(4) ?? '—'} />
                  <Metadata label="Timezone" value={payload.timezone ?? '—'} />
                  <Metadata label="Days" value={String(rows.length)} />
                </dl>

                {selectedMeta && (
                  <p className="truncate font-mono text-xs text-slate-500">
                    {selectedMeta.name}
                  </p>
                )}

                <TempChart rows={rows} />
                <DataTable rows={rows} />
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}

function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-50 px-3 py-2">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-800">{value}</dd>
    </div>
  )
}
