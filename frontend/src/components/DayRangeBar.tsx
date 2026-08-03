/** A single day's range, as a horizontal bar instead of a line chart — a
 *  3-point line chart communicates nothing, but a min-max track with the
 *  feels-like readings marked on the same axis reads at a glance and needs
 *  no legend, since every point is labelled directly.
 *
 *  All positioning comes from `dayRangeGeometry` (lib/transform.ts), the
 *  tested pure layer; this component only turns those percentages into
 *  markup and handles the presentation-only concerns (a visible minimum
 *  width for a zero-span range, label anchoring near the track's edges). */

import { dayRangeGeometry } from '../lib/transform'
import type { ChartColors } from '../lib/theme'
import type { DailyRow } from '../lib/transform'

function formatTemp(value: number | null): string {
  return value === null ? '—' : `${value}°C`
}

/** Labels anchor to the track's edge instead of centering past it, so a
 *  reading that lands at/near 0% or 100% never clips off the card. */
function anchorFor(pct: number): 'start' | 'center' | 'end' {
  if (pct <= 12) return 'start'
  if (pct >= 88) return 'end'
  return 'center'
}

const TRANSLATE: Record<'start' | 'center' | 'end', string> = {
  start: '0%',
  center: '-50%',
  end: '-100%',
}

function PointLabel({
  pct,
  text,
  color,
  offsetPx = 0,
}: {
  pct: number
  text: string
  color: string
  offsetPx?: number
}) {
  const anchor = anchorFor(pct)
  return (
    <span
      className="absolute top-0 text-[11px] leading-tight font-medium whitespace-nowrap"
      style={{
        left: `calc(${pct}% + ${offsetPx}px)`,
        transform: `translateX(${TRANSLATE[anchor]})`,
        color,
      }}
    >
      {text}
    </span>
  )
}

function Dot({
  pct,
  color,
  small = false,
  offsetPx = 0,
}: {
  pct: number
  color: string
  small?: boolean
  offsetPx?: number
}) {
  const size = small ? 'h-2 w-2' : 'h-3 w-3'
  return (
    <span
      className={`absolute top-1/2 ${size} shrink-0 rounded-full ring-2 ring-[var(--surface-card)]`}
      style={{
        left: `calc(${pct}% + ${offsetPx}px)`,
        transform: 'translate(-50%, -50%)',
        backgroundColor: color,
      }}
      aria-hidden="true"
    />
  )
}

export function DayRangeBar({ row, colors }: { row: DailyRow; colors: ChartColors }) {
  const geometry = dayRangeGeometry(row)
  const hasAnyPoint = [
    geometry.minPct,
    geometry.maxPct,
    geometry.feelsMinPct,
    geometry.feelsMaxPct,
  ].some((value) => value !== null)

  if (!hasAnyPoint) {
    return (
      <p className="rounded-md border border-dashed border-[var(--grid-line)] px-4 py-6 text-center text-sm text-[var(--ink-muted)]">
        No readings for this day.
      </p>
    )
  }

  const hasRange = geometry.minPct !== null && geometry.maxPct !== null
  const rangeLeft = hasRange ? Math.min(geometry.minPct!, geometry.maxPct!) : 0
  // A minimum visible width so an equal min/max (zero-width range) still
  // renders as a mark, not nothing — purely a presentation floor, not part
  // of the tested geometry.
  const rangeWidth = hasRange
    ? Math.max(Math.abs(geometry.maxPct! - geometry.minPct!), 2)
    : 0

  // Equal min/max land the two dots and labels on the exact same point —
  // nudge them a few px apart (not a position change, just legibility) so
  // both stay visible instead of one occluding the other.
  const degenerateRange = hasRange && geometry.minPct === geometry.maxPct
  const minOffsetPx = degenerateRange ? -6 : 0
  const maxOffsetPx = degenerateRange ? 6 : 0

  return (
    <div className="px-2 py-1">
      {/* Feels-like labels, above the track. */}
      <div className="relative h-4">
        {geometry.feelsMaxPct !== null && (
          <PointLabel
            pct={geometry.feelsMaxPct}
            text={`Feels ${formatTemp(row.feelsMax)}`}
            color={colors.feelsMax}
          />
        )}
        {geometry.feelsMinPct !== null && (
          <PointLabel
            pct={geometry.feelsMinPct}
            text={`Feels ${formatTemp(row.feelsMin)}`}
            color={colors.feelsMin}
          />
        )}
      </div>

      {/* The track: filled min-max range plus all four points. */}
      <div className="relative mt-3 mb-3 h-2 rounded-full bg-[var(--grid-line)]">
        {hasRange && (
          <div
            className="absolute top-0 h-2 rounded-full"
            style={{
              left: `${rangeLeft}%`,
              width: `${rangeWidth}%`,
              backgroundColor: colors.seriesMax,
              opacity: 0.22,
            }}
            aria-hidden="true"
          />
        )}
        {geometry.feelsMinPct !== null && <Dot pct={geometry.feelsMinPct} color={colors.feelsMin} small />}
        {geometry.feelsMaxPct !== null && <Dot pct={geometry.feelsMaxPct} color={colors.feelsMax} small />}
        {geometry.minPct !== null && (
          <Dot pct={geometry.minPct} color={colors.seriesMin} offsetPx={minOffsetPx} />
        )}
        {geometry.maxPct !== null && (
          <Dot pct={geometry.maxPct} color={colors.seriesMax} offsetPx={maxOffsetPx} />
        )}
      </div>

      {/* Min/max labels, below the track. */}
      <div className="relative h-4">
        {geometry.minPct !== null && (
          <PointLabel
            pct={geometry.minPct}
            text={`Min ${formatTemp(row.tempMin)}`}
            color={colors.seriesMin}
            offsetPx={minOffsetPx}
          />
        )}
        {geometry.maxPct !== null && (
          <PointLabel
            pct={geometry.maxPct}
            text={`Max ${formatTemp(row.tempMax)}`}
            color={colors.seriesMax}
            offsetPx={maxOffsetPx}
          />
        )}
      </div>
    </div>
  )
}
