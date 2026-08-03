import { useEffect, useState } from 'react'

import { clampPage, pageCount, paginate, type DailyRow } from '../lib/transform'

const PAGE_SIZES = [10, 20, 50]

const COLUMNS: { key: keyof DailyRow; label: string }[] = [
  { key: 'date', label: 'Date' },
  { key: 'tempMax', label: 'Max °C' },
  { key: 'tempMin', label: 'Min °C' },
  { key: 'feelsMax', label: 'Feels max °C' },
  { key: 'feelsMin', label: 'Feels min °C' },
]

export function DataTable({ rows }: { rows: DailyRow[] }) {
  const [pageSize, setPageSize] = useState(10)
  const [page, setPage] = useState(1)

  // A file with fewer rows, or a larger page size, can strand us past the end.
  useEffect(() => {
    setPage((current) => clampPage(current, rows.length, pageSize))
  }, [rows.length, pageSize])

  // Compute effective page synchronously to avoid empty-table flash.
  const effectivePage = clampPage(page, rows.length, pageSize)
  const totalPages = pageCount(rows.length, pageSize)
  const visible = paginate(rows, effectivePage, pageSize)

  if (rows.length === 0) {
    return <p className="py-8 text-center text-sm text-[var(--ink-muted)]">Nothing to tabulate.</p>
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-md border border-[var(--grid-line)]">
        <table className="min-w-full divide-y divide-[var(--grid-line)] text-sm">
          <thead className="bg-[var(--surface-page)]">
            <tr>
              {COLUMNS.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className="px-3 py-2 text-left font-medium whitespace-nowrap text-[var(--ink-secondary)]"
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--grid-line)]">
            {visible.map((row) => (
              <tr key={row.date} className="hover:bg-[var(--surface-page)]">
                {COLUMNS.map((column) => {
                  const value = row[column.key]
                  const numeric = column.key !== 'date'
                  return (
                    <td
                      key={column.key}
                      className={`px-3 py-2 whitespace-nowrap text-[var(--ink-primary)] ${
                        numeric ? 'tabular-nums' : ''
                      }`}
                    >
                      {value === null ? <span className="text-[var(--ink-muted)]">—</span> : value}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <label className="flex items-center gap-2 text-[var(--ink-secondary)]">
          Rows per page
          <select
            value={pageSize}
            onChange={(event) => setPageSize(Number(event.target.value))}
            className="rounded-md border border-[var(--axis-line)] bg-[var(--surface-card)] px-2 py-1 text-[var(--ink-primary)]"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            disabled={effectivePage === 1}
            className="rounded-md border border-[var(--axis-line)] px-3 py-1 text-[var(--ink-secondary)] disabled:opacity-40"
          >
            Previous
          </button>
          <span className="tabular-nums text-[var(--ink-secondary)]">
            Page {effectivePage} of {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
            disabled={effectivePage === totalPages}
            className="rounded-md border border-[var(--axis-line)] px-3 py-1 text-[var(--ink-secondary)] disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
