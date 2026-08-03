type Kind = 'error' | 'success' | 'info'

const STYLES: Record<Kind, string> = {
  error:
    'bg-[var(--status-error-bg)] text-[var(--status-error-text)] border-[var(--status-error-border)]',
  success:
    'bg-[var(--status-success-bg)] text-[var(--status-success-text)] border-[var(--status-success-border)]',
  info: 'bg-[var(--status-info-bg)] text-[var(--status-info-text)] border-[var(--status-info-border)]',
}

export function StatusBanner({ kind, message }: { kind: Kind; message: string }) {
  return (
    <div
      role={kind === 'error' ? 'alert' : 'status'}
      className={`rounded-md border px-3 py-2 text-sm break-words ${STYLES[kind]}`}
    >
      {message}
    </div>
  )
}
