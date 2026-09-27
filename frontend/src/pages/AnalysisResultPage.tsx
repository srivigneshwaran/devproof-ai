import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getAnalysis, type AnalysisResult } from '../api/analysisApi'
import { generateFixes } from '../api/fixApi'
import { FileRelevanceCard } from '../components/FileRelevanceCard'
import { RootCauseCard } from '../components/RootCauseCard'

export function AnalysisResultPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [apiError, setApiError] = useState<string | null>(null)

  const [suggesting, setSuggesting] = useState(false)
  const [suggestError, setSuggestError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    getAnalysis(id)
      .then(setAnalysis)
      .catch((e: Error) => setApiError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  async function handleSuggestFix() {
    if (!id || suggesting) return
    setSuggestError(null)
    setSuggesting(true)
    try {
      await generateFixes(id)
      navigate(`/analysis/${id}/fix`)
    } catch (e) {
      setSuggestError(e instanceof Error ? e.message : 'An unexpected error occurred.')
      setSuggesting(false)
    }
  }

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center gap-3 text-gray-500 py-16 justify-center">
        <span className="h-5 w-5 rounded-full border-2 border-gray-300 border-t-blue-600 animate-spin" />
        <span className="text-sm">Loading analysis results…</span>
      </div>
    )
  }

  // ── API error loading analysis ─────────────────────────────────────────────
  if (apiError) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <strong className="font-medium">Failed to load analysis: </strong>
          {apiError}
        </div>
      </div>
    )
  }

  // ── No data (shouldn't normally happen) ───────────────────────────────────
  if (!analysis) return null

  const hasFiles = analysis.relevant_files.length > 0
  const hasCauses = analysis.root_causes.length > 0

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Analysis Results</h1>
        <p className="mt-1 text-sm text-gray-500">
          Relevant files ranked by confidence, and identified root causes.
        </p>
      </div>

      {/* ── Relevant Files ──────────────────────────────────────────────── */}
      <section>
        <h2 className="text-base font-semibold text-gray-800 mb-3">Relevant Files</h2>
        {hasFiles ? (
          <div className="space-y-2">
            {analysis.relevant_files.map((file) => (
              <FileRelevanceCard key={file.path} file={file} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500 italic">No relevant files identified.</p>
        )}
      </section>

      {/* ── Root Causes ─────────────────────────────────────────────────── */}
      <section>
        <h2 className="text-base font-semibold text-gray-800 mb-3">Root Causes</h2>
        {hasCauses ? (
          <div className="space-y-2">
            {analysis.root_causes.map((cause, i) => (
              <RootCauseCard key={i} cause={cause} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500 italic">No root causes identified.</p>
        )}
      </section>

      {/* ── Suggest Fix error ───────────────────────────────────────────── */}
      {suggestError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <strong className="font-medium">Error: </strong>
          {suggestError}
        </div>
      )}

      {/* ── CTA ─────────────────────────────────────────────────────────── */}
      <div className="flex justify-end pt-2">
        <button
          type="button"
          onClick={handleSuggestFix}
          disabled={suggesting || !hasFiles}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        >
          {suggesting ? (
            <>
              <span className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />
              Generating fix…
            </>
          ) : (
            <>
              Suggest Fix
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
              </svg>
            </>
          )}
        </button>
      </div>
    </div>
  )
}
