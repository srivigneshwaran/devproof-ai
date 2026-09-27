interface Props {
  output: string
  /** Optional max height in Tailwind class form — defaults to max-h-80 */
  maxHeightClass?: string
}

/**
 * Renders raw terminal / pytest stdout in a dark monospace scrollable box.
 */
export function TerminalOutput({ output, maxHeightClass = 'max-h-80' }: Props) {
  if (!output) {
    return (
      <div className={`rounded-lg bg-gray-900 px-4 py-3 font-mono text-xs text-gray-500 ${maxHeightClass}`}>
        No output captured.
      </div>
    )
  }

  return (
    <div className={`rounded-lg bg-gray-900 overflow-auto ${maxHeightClass}`}>
      <pre className="p-4 m-0 font-mono text-xs leading-5 text-gray-100 whitespace-pre-wrap break-words">
        {output}
      </pre>
    </div>
  )
}
