interface Props {
  original: string
  suggested: string
}

/**
 * Side-by-side diff view.
 * Lines present in `original` but not `suggested` are styled red (–).
 * Lines present in `suggested` but not `original` are styled green (+).
 * Lines identical in both are rendered neutral.
 *
 * For the MVP we do a simple line-by-line comparison: each line is
 * colour-coded based on whether it exists in the opposite column at the
 * same position.  This keeps the component dependency-free while still
 * making additions and removals visually distinct.
 */
export function DiffViewer({ original, suggested }: Props) {
  const origLines = original.split('\n')
  const sugLines = suggested.split('\n')
  const maxLen = Math.max(origLines.length, sugLines.length)

  return (
    <div className="grid grid-cols-2 gap-0 rounded-lg border border-gray-200 overflow-hidden text-xs font-mono">
      {/* Column headers */}
      <div className="bg-red-50 border-b border-r border-gray-200 px-3 py-1.5 text-xs font-semibold text-red-700 tracking-wide uppercase">
        Original
      </div>
      <div className="bg-green-50 border-b border-gray-200 px-3 py-1.5 text-xs font-semibold text-green-700 tracking-wide uppercase">
        Suggested
      </div>

      {/* Lines */}
      <div className="bg-red-50/40 border-r border-gray-200 overflow-x-auto">
        <pre className="p-3 leading-5 whitespace-pre m-0">
          {Array.from({ length: maxLen }, (_, i) => {
            const line = origLines[i] ?? ''
            const isMissing = i >= origLines.length
            const isDifferent = !isMissing && origLines[i] !== (sugLines[i] ?? '')
            return (
              <div
                key={i}
                className={
                  isMissing
                    ? 'text-gray-300'
                    : isDifferent
                    ? 'bg-red-100 text-red-800'
                    : 'text-gray-700'
                }
              >
                <span className="select-none mr-2 text-gray-400">
                  {isMissing ? ' ' : '-'}
                </span>
                {line || '\u00a0'}
              </div>
            )
          })}
        </pre>
      </div>

      <div className="bg-green-50/40 overflow-x-auto">
        <pre className="p-3 leading-5 whitespace-pre m-0">
          {Array.from({ length: maxLen }, (_, i) => {
            const line = sugLines[i] ?? ''
            const isMissing = i >= sugLines.length
            const isDifferent = !isMissing && sugLines[i] !== (origLines[i] ?? '')
            return (
              <div
                key={i}
                className={
                  isMissing
                    ? 'text-gray-300'
                    : isDifferent
                    ? 'bg-green-100 text-green-800'
                    : 'text-gray-700'
                }
              >
                <span className="select-none mr-2 text-gray-400">
                  {isMissing ? ' ' : '+'}
                </span>
                {line || '\u00a0'}
              </div>
            )
          })}
        </pre>
      </div>
    </div>
  )
}
