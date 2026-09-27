import { useState } from 'react'

interface Props {
  code: string
  filename?: string
  language?: string
}

/**
 * Renders a code block with a monospace pre/code, optional filename label,
 * and a copy-to-clipboard button.
 */
export function CodeBlock({ code, filename, language }: Props) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden text-sm">
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2 px-3 py-1.5 bg-gray-100 border-b border-gray-200">
        <div className="flex items-center gap-2 min-w-0">
          {filename && (
            <span className="font-mono text-xs font-medium text-gray-700 truncate">{filename}</span>
          )}
          {language && (
            <span className="text-xs text-gray-400 uppercase tracking-wide">{language}</span>
          )}
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="shrink-0 inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-gray-600 hover:bg-gray-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors"
          aria-label="Copy code"
        >
          {copied ? (
            <>
              <svg className="h-3.5 w-3.5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
              <span className="text-green-700">Copied!</span>
            </>
          ) : (
            <>
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5a3.375 3.375 0 00-3.375-3.375H9.75" />
              </svg>
              Copy
            </>
          )}
        </button>
      </div>

      {/* Code body */}
      <pre className="bg-gray-900 text-gray-100 overflow-x-auto overflow-y-auto p-4 m-0 font-mono text-xs leading-5 max-h-96">
        <code>{code}</code>
      </pre>
    </div>
  )
}
