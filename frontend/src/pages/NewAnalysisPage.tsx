import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ProjectSelector } from '../components/ProjectSelector'
import { FileUpload } from '../components/FileUpload'
import { uploadFiles } from '../api/projectsApi'
import { createSession } from '../api/sessionsApi'
import { runAnalysis } from '../api/analysisApi'

const MIN_DESC_CHARS = 20

type InputMode = 'project' | 'upload'

export function NewAnalysisPage() {
  const navigate = useNavigate()

  // Input mode
  const [inputMode, setInputMode] = useState<InputMode>('project')

  // Project selector
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)

  // File upload
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([])

  // Bug description
  const [bugDescription, setBugDescription] = useState('')

  // Submit state
  const [submitting, setSubmitting] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  // Inline validation errors (shown on submit attempt)
  const [touched, setTouched] = useState(false)

  // Derived validation
  const inputMissing =
    inputMode === 'project' ? selectedProjectId === null : uploadedFiles.length === 0
  const descTooShort = bugDescription.trim().length < MIN_DESC_CHARS

  const isValid = !inputMissing && !descTooShort

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setTouched(true)

    if (!isValid || submitting) return

    setApiError(null)
    setSubmitting(true)

    try {
      // Step 1: resolve project_id
      let projectId: string

      if (inputMode === 'upload') {
        // Upload the files first; the API returns session_file_paths but we still
        // need a project_id for createSession. We use the sentinel value "upload"
        // which the backend derives from the uploaded file workspace.
        await uploadFiles(uploadedFiles)
        projectId = 'upload'
      } else {
        projectId = selectedProjectId!
      }

      // Step 2: create session
      const session = await createSession({
        project_id: projectId,
        bug_description: bugDescription.trim(),
      })

      // Step 3: run analysis
      await runAnalysis(session.id)

      // Step 4: navigate to results
      navigate(`/analysis/${session.id}/results`)
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'An unexpected error occurred.')
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900">New Analysis</h1>
        <p className="mt-1 text-sm text-gray-500">
          Select a sample project or upload your own Python files, describe the bug, and let
          DevProof AI pinpoint the root cause.
        </p>
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-8">
        {/* ── Step 1: Input source ─────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-1 mb-4">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-600 text-white text-xs font-semibold shrink-0">
              1
            </span>
            <h2 className="text-base font-semibold text-gray-800 ml-2">Choose your code source</h2>
          </div>

          {/* Tab switcher */}
          <div className="flex rounded-lg border border-gray-200 bg-gray-100 p-1 w-fit mb-4" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={inputMode === 'project'}
              onClick={() => {
                setInputMode('project')
                setTouched(false)
              }}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                inputMode === 'project'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Sample Project
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={inputMode === 'upload'}
              onClick={() => {
                setInputMode('upload')
                setTouched(false)
              }}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                inputMode === 'upload'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Upload Files
            </button>
          </div>

          {/* Content per mode */}
          {inputMode === 'project' ? (
            <>
              <ProjectSelector
                selectedId={selectedProjectId}
                onSelect={setSelectedProjectId}
              />
              {touched && inputMissing && (
                <p className="mt-2 text-xs text-red-600">Please select a sample project.</p>
              )}
            </>
          ) : (
            <>
              <FileUpload files={uploadedFiles} onChange={setUploadedFiles} />
              {touched && inputMissing && (
                <p className="mt-2 text-xs text-red-600">
                  Please upload at least one .py file.
                </p>
              )}
            </>
          )}
        </section>

        {/* ── Step 2: Bug description ──────────────────────────────── */}
        <section>
          <div className="flex items-center gap-1 mb-4">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-600 text-white text-xs font-semibold shrink-0">
              2
            </span>
            <h2 className="text-base font-semibold text-gray-800 ml-2">Describe the bug</h2>
          </div>

          <textarea
            id="bug-description"
            value={bugDescription}
            onChange={(e) => setBugDescription(e.target.value)}
            rows={5}
            placeholder="e.g. The discount is being applied before tax, causing customers to be overcharged when both a discount and tax are present on the same order."
            className={`w-full rounded-lg border px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 resize-none transition-colors ${
              touched && descTooShort
                ? 'border-red-400 bg-red-50'
                : 'border-gray-300 bg-white'
            }`}
          />

          <div className="mt-1 flex justify-between items-center">
            {touched && descTooShort ? (
              <p className="text-xs text-red-600">
                Description must be at least {MIN_DESC_CHARS} characters.
              </p>
            ) : (
              <span />
            )}
            <span
              className={`text-xs ml-auto ${
                bugDescription.trim().length >= MIN_DESC_CHARS
                  ? 'text-gray-400'
                  : 'text-gray-400'
              }`}
            >
              {bugDescription.trim().length}/{MIN_DESC_CHARS} min
            </span>
          </div>
        </section>

        {/* ── API error banner ─────────────────────────────────────── */}
        {apiError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <strong className="font-medium">Error: </strong>
            {apiError}
          </div>
        )}

        {/* ── Submit ───────────────────────────────────────────────── */}
        <div className="flex items-center justify-end pt-2">
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? (
              <>
                <span className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                Analyzing…
              </>
            ) : (
              'Analyze'
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
