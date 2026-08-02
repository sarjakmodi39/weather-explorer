import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { DailyRow } from '../lib/transform'

const SERIES = [
  { key: 'tempMax', name: 'Max temp', color: '#dc2626' },
  { key: 'tempMin', name: 'Min temp', color: '#2563eb' },
  { key: 'feelsMax', name: 'Feels-like max', color: '#f97316' },
  { key: 'feelsMin', name: 'Feels-like min', color: '#0891b2' },
] as const

export function TempChart({ rows }: { rows: DailyRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-slate-500">
        No daily data in this file.
      </p>
    )
  }

  return (
    <div className="h-72 w-full sm:h-80">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 8, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" minTickGap={24} />
          <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" unit="°" width={48} />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 6 }}
            formatter={(value) => (value === null ? '—' : `${value}°C`)}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {SERIES.map((series) => (
            <Line
              key={series.key}
              type="monotone"
              dataKey={series.key}
              name={series.name}
              stroke={series.color}
              dot={false}
              strokeWidth={2}
              // Leave a visible gap where a reading is null rather than
              // drawing a straight line through missing data.
              connectNulls={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
