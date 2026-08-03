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
    <section className="rounded-lg border border-[var(--grid-line)] bg-[var(--surface-card)] p-4 shadow-sm sm:p-5">
      <div className="mb-4 flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-[var(--ink-primary)]">Stored files</h2>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="rounded-md border border-[var(--axis-line)] px-3 py-1 text-sm text-[var(--ink-secondary)] hover:bg-[var(--surface-page)] disabled:opacity-50"
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
                  className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
                    selected
                      ? 'border-[var(--accent-soft-border)] bg-[var(--accent-soft)]'
                      : 'border-transparent hover:bg-[var(--surface-page)]'
                  }`}
                >
                  <span
                    className="block font-mono text-[11px] leading-snug break-all text-[var(--ink-secondary)]"
                    title={file.name}
                  >
                    {file.name}
                  </span>
                  <span className="mt-1 block text-xs text-[var(--ink-muted)]">
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
