import type { RelevantFile } from '../api/analysisApi'

interface Props {
  file: RelevantFile
}

export function FileRelevanceCard({ file }: Props) {
  const pct = Math.round(file.confidence * 100)

  return (
    <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 space-y-2">
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-sm font-medium text-gray-900 truncate">{file.path}</span>
        <span className="shrink-0 text-sm font-semibold text-blue-600">{pct}%</span>
      </div>

      {/* Confidence bar */}
      <div className="h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
        <div
          className="h-full rounded-full bg-blue-500 transition-all"
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${pct}% confidence`}
        />
      </div>

      {/* Reason */}
      {file.reason && (
        <p className="text-xs text-gray-500">{file.reason}</p>
      )}
    </div>
  )
}
