import type { RootCause } from '../api/analysisApi'

interface Props {
  cause: RootCause
}

export function RootCauseCard({ cause }: Props) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 space-y-2">
      {/* Description */}
      <p className="text-sm text-gray-800">{cause.description}</p>

      {/* Badges row */}
      <div className="flex items-center gap-2 flex-wrap">
        {cause.file && (
          <span className="inline-flex items-center rounded-md bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-700 border border-gray-200">
            {cause.file}
          </span>
        )}
        {cause.line_hint != null && cause.line_hint > 0 && (
          <span className="inline-flex items-center rounded-md bg-amber-100 px-2 py-0.5 text-xs text-amber-800 border border-amber-200">
            line {cause.line_hint}
          </span>
        )}
      </div>
    </div>
  )
}
