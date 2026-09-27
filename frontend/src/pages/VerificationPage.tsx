import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { runVerification } from '../api/verifyApi'
import type { VerificationReport } from '../api/reportApi'
import { CodeBlock } from '../components/CodeBlock'
import { TerminalOutput } from '../components/TerminalOutput'
import { VerdictBadge } from '../components/VerdictBadge'

export function VerificationPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [report, setReport] = useState<VerificationReport | null>(null)

  async function handleRunVerification() {
    if (!id || running) return
    setRunError(null)
    setRunning(true)
    try {
      const result = await runVerification(id)
      setReport(result)
    } catch (e) {
      setRunError(e instanceof Error ? e.message : 'An unexpected error occurred.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Verification</h1>
        <p className="mt-1 text-sm text-gray-500">
          Generate tests for the approved fix and run them against the codebase.
        </p>
      </div>

      {/* ── Run CTA (shown before result) ────────────────────────────────── */}
      {!report && (
        <div className="rounded-lg border border-gray-200 bg-white p-6 flex flex-col items-center gap-4 text-center">
          <div className="h-12 w-12 rounded-full bg-blue-50 flex items-center justify-center">
            <svg className="h-6 w-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 010 1.972l-11.54 6.347a1.125 1.125 0 01-1.667-.986V5.653z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900">Ready to verify the approved fix</p>
            <p className="mt-1 text-xs text-gray-500">
              This will generate pytest tests, run them, and produce a full verification report.
            </p>
          </div>

          {/* Run error */}
          {runError && (
            <div className="w-full rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 text-left">
              <strong className="font-medium">Error: </strong>
              {runError}
            </div>
          )}

          <button
            type="button"
            onClick={handleRunVerification}
            disabled={running}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          >
            {running ? (
              <>
                <span className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                Running verification…
              </>
            ) : (
              <>
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 010 1.972l-11.54 6.347a1.125 1.125 0 01-1.667-.986V5.653z" />
                </svg>
                Run Full Verification
              </>
            )}
          </button>
        </div>
      )}

      {/* ── Results (shown after successful run) ─────────────────────────── */}
      {report && (
        <>
          {/* Verdict + pass/fail counts */}
          <div className="rounded-lg border border-gray-200 bg-white px-5 py-4 flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              <VerdictBadge verdict={report.verdict} />
              <div className="text-sm text-gray-500">
                <span className="font-medium text-green-700">{report.tests_passed} passed</span>
                {report.tests_failed > 0 && (
                  <>
                    {' · '}
                    <span className="font-medium text-red-700">{report.tests_failed} failed</span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Generated test files */}
          {report.tests_generated && report.tests_generated.length > 0 && (
            <section>
              <h2 className="text-base font-semibold text-gray-800 mb-3">Generated Tests</h2>
              <div className="space-y-4">
                {report.tests_generated.map((t) => (
                  <CodeBlock key={t.file} code={t.code} filename={t.file} language="python" />
                ))}
              </div>
            </section>
          )}

          {/* Terminal output */}
          <section>
            <h2 className="text-base font-semibold text-gray-800 mb-3">Test Run Output</h2>
            <TerminalOutput output={report.test_output} maxHeightClass="max-h-96" />
          </section>

          {/* Run error (shown after result if something re-runs) */}
          {runError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <strong className="font-medium">Error: </strong>
              {runError}
            </div>
          )}

          {/* View Report CTA */}
          <div className="flex justify-end pt-2">
            <button
              type="button"
              onClick={() => navigate(`/analysis/${id}/report`)}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors"
            >
              View Report
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
              </svg>
            </button>
          </div>
        </>
      )}
    </div>
  )
}
