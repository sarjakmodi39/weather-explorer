import type { StoredFileMeta } from '../types'
import { StatusBanner } from './StatusBanner'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  const parsed = new Date(iso)
  return Number.isNaN(parsed.valueOf()) ? iso : parsed.toLocaleString()
}

interface Props {
  files: StoredFileMeta[]
  loading: boolean
  error: string | null
  selectedName: string | null
  onSelect: (name: string) => void
  onRefresh: () => void
}

export function FileList({
  files,
  loading,
  error,
  selectedName,
  onSelect,
  onRefresh,
}: Props) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-slate-800">Stored files</h2>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-50"
        >
          {loading ? 'Loading…' : 'Browse'}
        </button>
      </div>

      {error && <StatusBanner kind="error" message={error} />}

      {!error && !loading && files.length === 0 && (
        <StatusBanner kind="info" message="No files stored yet. Fetch some data to get started." />
      )}

      {files.length > 0 && (
        <ul className="max-h-96 space-y-1 overflow-y-auto">
          {files.map((file) => {
            const selected = file.name === selectedName
            return (
              <li key={file.name}>
                <button
                  type="button"
                  onClick={() => onSelect(file.name)}
                  aria-current={selected}
                  className={`w-full rounded-md border px-3 py-2 text-left transition ${
                    selected
                      ? 'border-sky-300 bg-sky-50'
                      : 'border-transparent hover:bg-slate-50'
                  }`}
                >
                  <span className="block truncate font-mono text-xs text-slate-700">
                    {file.name}
                  </span>
                  <span className="mt-0.5 block text-xs text-slate-500">
                    {formatSize(file.size)} · {formatDate(file.created_at)}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
