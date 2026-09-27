import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getFixes, approveFix, type Fix } from '../api/fixApi'
import { DiffViewer } from '../components/DiffViewer'

export function FixSuggestionPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [fixes, setFixes] = useState<Fix[]>([])
  const [loading, setLoading] = useState(true)
  const [apiError, setApiError] = useState<string | null>(null)

  // Approval state
  const [approving, setApproving] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  // Rejection feedback
  const [showFeedback, setShowFeedback] = useState(false)
  const [feedback, setFeedback] = useState('')

  useEffect(() => {
    if (!id) return
    getFixes(id)
      .then((data) => setFixes(data.fixes))
      .catch((e: Error) => setApiError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  async function handleApprove() {
    if (!id || approving) return
    setActionError(null)
    setApproving(true)
    try {
      await approveFix(id, true)
      navigate(`/analysis/${id}/verify`)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'An unexpected error occurred.')
      setApproving(false)
    }
  }

  function handleRejectClick() {
    // Toggle the feedback panel; if already shown and empty, submit immediately
    if (!showFeedback) {
      setShowFeedback(true)
      return
    }
    handleRejectSubmit()
  }

  async function handleRejectSubmit() {
    if (!id || approving) return
    setActionError(null)
    setApproving(true)
    try {
      await approveFix(id, false, feedback.trim() || undefined)
      navigate('/analysis/new')
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'An unexpected error occurred.')
      setApproving(false)
    }
  }

  // ── Loading ─────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center gap-3 text-gray-500 py-16 justify-center">
        <span className="h-5 w-5 rounded-full border-2 border-gray-300 border-t-blue-600 animate-spin" />
        <span className="text-sm">Loading fix suggestions…</span>
      </div>
    )
  }

  // ── Error loading fixes ──────────────────────────────────────────────────────
  if (apiError) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <strong className="font-medium">Failed to load fixes: </strong>
          {apiError}
        </div>
      </div>
    )
  }

  // ── Empty fixes ──────────────────────────────────────────────────────────────
  if (fixes.length === 0) {
    return (
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-semibold text-gray-900 mb-4">Fix Suggestion</h1>
        <p className="text-sm text-gray-500 italic">No fix suggestions available for this session.</p>
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Fix Suggestion</h1>
        <p className="mt-1 text-sm text-gray-500">
          Review the proposed changes below. Approve to run full verification, or reject with
          optional feedback to start over.
        </p>
      </div>

      {/* ── Fix cards ─────────────────────────────────────────────────────── */}
      {fixes.map((fix) => (
        <section key={fix.id} className="rounded-lg border border-gray-200 bg-white overflow-hidden">
          {/* Fix header */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-200 bg-gray-50">
            <svg className="h-4 w-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
            <span className="font-mono text-sm font-medium text-gray-800">{fix.file_path}</span>
          </div>

          {/* Diff viewer */}
          <div className="p-4">
            <DiffViewer original={fix.original} suggested={fix.suggested} />
          </div>

          {/* Explanation */}
          {fix.explanation && (
            <div className="px-4 pb-4">
              <div className="rounded-md bg-blue-50 border border-blue-100 px-3 py-2 text-sm text-blue-800">
                <span className="font-medium">Explanation: </span>
                {fix.explanation}
              </div>
            </div>
          )}
        </section>
      ))}

      {/* ── Action error ──────────────────────────────────────────────────── */}
      {actionError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <strong className="font-medium">Error: </strong>
          {actionError}
        </div>
      )}

      {/* ── Rejection feedback ────────────────────────────────────────────── */}
      {showFeedback && (
        <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-2">
          <label htmlFor="reject-feedback" className="block text-sm font-medium text-gray-700">
            Rejection feedback <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <textarea
            id="reject-feedback"
            rows={3}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Describe what was wrong or how it should be fixed…"
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400 resize-none"
          />
        </div>
      )}

      {/* ── Approval row ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-end gap-3 pt-2">
        {/* Reject button */}
        <button
          type="button"
          onClick={handleRejectClick}
          disabled={approving}
          className="inline-flex items-center gap-2 rounded-lg border border-red-300 bg-white px-5 py-2.5 text-sm font-semibold text-red-600 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        >
          {approving && showFeedback ? (
            <>
              <span className="h-4 w-4 rounded-full border-2 border-red-300 border-t-red-600 animate-spin" />
              Rejecting…
            </>
          ) : showFeedback ? (
            'Confirm Rejection'
          ) : (
            'Reject'
          )}
        </button>

        {/* Approve button */}
        <button
          type="button"
          onClick={handleApprove}
          disabled={approving}
          className="inline-flex items-center gap-2 rounded-lg bg-green-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-green-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-green-500 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        >
          {approving && !showFeedback ? (
            <>
              <span className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />
              Approving…
            </>
          ) : (
            <>
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
              Approve Fix
            </>
          )}
        </button>
      </div>
    </div>
  )
}
