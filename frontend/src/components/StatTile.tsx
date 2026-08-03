/** One figure in a stat-tile row. Used both for the file-level summary
 *  (warmest/coldest day, average swing) and, in TempChart, for the
 *  single-day fallback that replaces the line chart. Values are the
 *  font's default proportional figures — tabular-nums is reserved for
 *  table columns and axis ticks, where digits must align in a column. */

export function StatTile({
  label,
  value,
  sublabel,
  accent,
}: {
  label: string
  value: string
  sublabel?: string
  accent?: string
}) {
  return (
    <div className="rounded-lg border border-[var(--grid-line)] bg-[var(--surface-card)] px-4 py-3 shadow-sm">
      <dt className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-[var(--ink-muted)] uppercase">
        {accent && (
          <span
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: accent }}
            aria-hidden="true"
          />
        )}
        {label}
      </dt>
      <dd className="mt-1 text-2xl font-semibold tracking-tight text-[var(--ink-primary)]">{value}</dd>
      {sublabel && <p className="mt-0.5 text-xs text-[var(--ink-secondary)]">{sublabel}</p>}
    </div>
  )
}
