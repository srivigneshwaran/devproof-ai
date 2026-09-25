import { useRef } from 'react'

interface Props {
  files: File[]
  onChange: (files: File[]) => void
}

const MAX_FILES = 5

export function FileUpload({ files, onChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files ?? [])
    const merged = dedupe([...files, ...selected]).slice(0, MAX_FILES)
    onChange(merged)
    // Reset so the same file can be re-added after removal
    e.target.value = ''
  }

  function removeFile(name: string) {
    onChange(files.filter((f) => f.name !== name))
  }

  return (
    <div className="space-y-3">
      <div
        className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 px-6 py-8 text-center hover:border-blue-400 hover:bg-blue-50/30 transition-colors cursor-pointer"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload Python files"
      >
        <svg
          className="mb-2 h-8 w-8 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
          />
        </svg>
        <p className="text-sm font-medium text-gray-700">
          Click to upload <span className="text-blue-600">.py files</span>
        </p>
        <p className="mt-1 text-xs text-gray-400">Max {MAX_FILES} files</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".py"
          className="hidden"
          onChange={handleInputChange}
        />
      </div>

      {files.length > 0 && (
        <ul className="space-y-1">
          {files.map((file) => (
            <li
              key={file.name}
              className="flex items-center justify-between rounded-md border border-gray-200 bg-white px-3 py-2 text-sm"
            >
              <span className="flex items-center gap-2 text-gray-800 truncate">
                <svg
                  className="h-4 w-4 shrink-0 text-blue-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                  />
                </svg>
                {file.name}
              </span>
              <button
                type="button"
                onClick={() => removeFile(file.name)}
                className="ml-2 shrink-0 text-gray-400 hover:text-red-500 transition-colors"
                aria-label={`Remove ${file.name}`}
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function dedupe(files: File[]): File[] {
  const seen = new Set<string>()
  return files.filter((f) => {
    if (seen.has(f.name)) return false
    seen.add(f.name)
    return true
  })
}
