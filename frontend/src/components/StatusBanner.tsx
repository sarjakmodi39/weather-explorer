type Kind = 'error' | 'success' | 'info'

const STYLES: Record<Kind, string> = {
  error: 'bg-red-50 text-red-800 border-red-200',
  success: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  info: 'bg-slate-50 text-slate-700 border-slate-200',
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
