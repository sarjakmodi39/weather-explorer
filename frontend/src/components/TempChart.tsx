import { useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts'

import type { ChartColors } from '../lib/theme'
import type { DailyRow } from '../lib/transform'
import { StatTile } from './StatTile'

const SERIES = [
  { key: 'tempMax', name: 'Max temp', colorKey: 'seriesMax' },
  { key: 'tempMin', name: 'Min temp', colorKey: 'seriesMin' },
  { key: 'feelsMax', name: 'Feels-like max', colorKey: 'feelsMax' },
  { key: 'feelsMin', name: 'Feels-like min', colorKey: 'feelsMin' },
] as const satisfies readonly { key: keyof DailyRow; name: string; colorKey: keyof ChartColors }[]

const SERIES_KEYS = new Set<string>(SERIES.map((series) => series.key))

interface ChartRow extends DailyRow {
  /** Bottom of the stacked band — invisible, just a spacer up to the min. */
  swingBase: number | null
  /** Height of the stacked band — the visible max-min swing. */
  swingRange: number | null
}

function toChartRows(rows: DailyRow[]): ChartRow[] {
  return rows.map((row) => ({
    ...row,
    swingBase: row.tempMin,
    swingRange: row.tempMax !== null && row.tempMin !== null ? row.tempMax - row.tempMin : null,
  }))
}

function formatTemp(value: number | null): string {
  return value === null ? '—' : `${value}°C`
}

/** Tooltip payload values come through as `unknown` to Recharts' own types
 *  (string | number | array, per its ValueType) — narrow before formatting. */
function formatTooltipValue(value: unknown): string {
  return typeof value === 'number' ? `${value}°C` : '—'
}

function ChartTooltip({
  active,
  label,
  payload,
  colors,
}: TooltipContentProps & { colors: ChartColors }) {
  if (!active || !payload?.length) return null

  // The stacked band contributes two synthetic entries (base + range) that
  // exist only to draw the shaded swing — they are not one of the four
  // series the reader asked about, so they never appear in the tooltip.
  const entries = payload.filter((entry) => SERIES_KEYS.has(String(entry.dataKey)))
  if (entries.length === 0) return null

  return (
    <div
      className="rounded-md border px-3 py-2 text-xs shadow-sm"
      style={{
        backgroundColor: colors.surface,
        borderColor: colors.gridline,
        color: colors.inkPrimary,
      }}
    >
      <p className="mb-1 font-medium">{label}</p>
      <ul className="space-y-0.5">
        {entries.map((entry) => (
          <li key={String(entry.dataKey)} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: entry.color }}
              aria-hidden="true"
            />
            <span style={{ color: colors.inkSecondary }}>{entry.name}:</span>
            <span className="font-medium tabular-nums">{formatTooltipValue(entry.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function TempChart({ rows, colors }: { rows: DailyRow[]; colors: ChartColors }) {
  const chartData = useMemo(() => toChartRows(rows), [rows])

  if (rows.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-[var(--ink-muted)]">
        No daily data in this file.
      </p>
    )
  }

  // A single day is a headline number, not a trend: four lonely dots on a
  // line chart tell no story, so the number itself becomes the chart.
  if (rows.length === 1) {
    const [row] = rows
    return (
      <div className="space-y-3">
        <p className="text-sm text-[var(--ink-secondary)]">Single day of data — {row.date}</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Max temp" value={formatTemp(row.tempMax)} accent={colors.seriesMax} />
          <StatTile label="Min temp" value={formatTemp(row.tempMin)} accent={colors.seriesMin} />
          <StatTile
            label="Feels-like max"
            value={formatTemp(row.feelsMax)}
            accent={colors.feelsMax}
          />
          <StatTile
            label="Feels-like min"
            value={formatTemp(row.feelsMin)}
            accent={colors.feelsMin}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="h-80 w-full sm:h-96">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={colors.gridline} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: colors.inkMuted }}
            stroke={colors.axis}
            minTickGap={24}
            tickMargin={8}
          />
          <YAxis
            tick={{ fontSize: 11, fill: colors.inkMuted }}
            stroke={colors.axis}
            unit="°"
            width={48}
          />
          <Tooltip content={(props) => <ChartTooltip {...props} colors={colors} />} />
          <Legend wrapperStyle={{ fontSize: 12, color: colors.inkSecondary }} />

          {/* An invisible base up to the daily min, then the visible swing
             stacked on top of it: together they shade the max-min band so
             the daily range reads at a glance. Low opacity keeps it a wash,
             never a saturated block, with the four lines legible on top. */}
          <Area
            dataKey="swingBase"
            stackId="swing"
            stroke="none"
            fill="transparent"
            legendType="none"
            isAnimationActive={false}
            connectNulls={false}
            activeDot={false}
          />
          <Area
            dataKey="swingRange"
            name="Daily range"
            stackId="swing"
            stroke="none"
            fill={colors.seriesMax}
            fillOpacity={0.12}
            legendType="none"
            isAnimationActive={false}
            connectNulls={false}
            activeDot={false}
          />

          {SERIES.map((series) => (
            <Line
              key={series.key}
              type="monotone"
              dataKey={series.key}
              name={series.name}
              stroke={colors[series.colorKey]}
              dot={false}
              strokeWidth={2}
              isAnimationActive={false}
              // Leave a visible gap where a reading is null rather than
              // drawing a straight line through missing data.
              connectNulls={false}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
