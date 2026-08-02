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

  const totalPages = pageCount(rows.length, pageSize)
  const visible = paginate(rows, page, pageSize)

  if (rows.length === 0) {
    return <p className="py-8 text-center text-sm text-slate-500">Nothing to tabulate.</p>
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-md border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              {COLUMNS.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className="px-3 py-2 text-left font-medium whitespace-nowrap text-slate-600"
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {visible.map((row) => (
              <tr key={row.date} className="hover:bg-slate-50">
                {COLUMNS.map((column) => {
                  const value = row[column.key]
                  return (
                    <td
                      key={column.key}
                      className="px-3 py-2 whitespace-nowrap text-slate-700"
                    >
                      {value === null ? <span className="text-slate-400">—</span> : value}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <label className="flex items-center gap-2 text-slate-600">
          Rows per page
          <select
            value={pageSize}
            onChange={(event) => setPageSize(Number(event.target.value))}
            className="rounded-md border border-slate-300 px-2 py-1"
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
            disabled={page === 1}
            className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-slate-600">
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
            disabled={page === totalPages}
            className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
