import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getReport } from '../api/reportApi'
import type { VerificationReport } from '../api/reportApi'
import { VerdictBadge } from '../components/VerdictBadge'
import { FileRelevanceCard } from '../components/FileRelevanceCard'
import { RootCauseCard } from '../components/RootCauseCard'
import { DiffViewer } from '../components/DiffViewer'
import { CodeBlock } from '../components/CodeBlock'

// ── Collapsible section helper ─────────────────────────────────────────────

interface CollapsibleSectionProps {
  title: string
  count?: number
  children: React.ReactNode
  defaultOpen?: boolean
}

function CollapsibleSection({ title, count, children, defaultOpen = false }: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-5 py-3.5 text-left hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500 transition-colors"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-800">{title}</span>
          {count !== undefined && (
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
              {count}
            </span>
          )}
        </div>
        <svg
          className={`h-4 w-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-gray-200 px-5 py-4 space-y-3">
          {children}
        </div>
      )}
    </div>
  )
}

// ── ReportPage ─────────────────────────────────────────────────────────────

export function ReportPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [report, setReport] = useState<VerificationReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [apiError, setApiError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!id) return
    getReport(id)
      .then(setReport)
      .catch((e: Error) => setApiError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  function handleCopyJson() {
    if (!report) return
    navigator.clipboard.writeText(JSON.stringify(report, null, 2)).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  // ── Loading ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center gap-3 text-gray-500 py-16 justify-center">
        <span className="h-5 w-5 rounded-full border-2 border-gray-300 border-t-blue-600 animate-spin" />
        <span className="text-sm">Loading report…</span>
      </div>
    )
  }

  // ── API error ──────────────────────────────────────────────────────────────
  if (apiError) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <strong className="font-medium">Failed to load report: </strong>
          {apiError}
        </div>
      </div>
    )
  }

  // ── No data ────────────────────────────────────────────────────────────────
  if (!report) return null

  const formattedDate = new Date(report.created_at).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Verification Report</h1>
          <p className="mt-1 text-sm text-gray-500">
            {report.project_name} · {formattedDate}
          </p>
        </div>
        <VerdictBadge verdict={report.verdict} />
      </div>

      {/* ── Summary card ────────────────────────────────────────────────── */}
      <div className="rounded-lg border border-gray-200 bg-white px-5 py-4 space-y-3">
        <div className="flex items-center gap-4 flex-wrap text-sm">
          <span className="font-medium text-gray-700">Tests:</span>
          <span className="text-green-700 font-semibold">{report.tests_passed} passed</span>
          {report.tests_failed > 0 && (
            <span className="text-red-700 font-semibold">{report.tests_failed} failed</span>
          )}
        </div>

        {report.summary && (
          <p className="text-sm text-gray-700 leading-relaxed">{report.summary}</p>
        )}

        <div className="text-xs text-gray-400">
          <strong className="font-medium text-gray-500">Bug description:</strong>{' '}
          {report.bug_description}
        </div>
      </div>

      {/* ── Collapsible sections ─────────────────────────────────────────── */}

      {/* Relevant Files */}
      <CollapsibleSection
        title="Relevant Files"
        count={report.relevant_files?.length ?? 0}
        defaultOpen={true}
      >
        {report.relevant_files && report.relevant_files.length > 0 ? (
          <div className="space-y-2">
            {report.relevant_files.map((file) => (
              <FileRelevanceCard key={file.path} file={file} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500 italic">No relevant files recorded.</p>
        )}
      </CollapsibleSection>

      {/* Root Causes */}
      <CollapsibleSection
        title="Root Causes"
        count={report.root_causes?.length ?? 0}
      >
        {report.root_causes && report.root_causes.length > 0 ? (
          <div className="space-y-2">
            {report.root_causes.map((cause, i) => (
              <RootCauseCard key={i} cause={cause} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500 italic">No root causes recorded.</p>
        )}
      </CollapsibleSection>

      {/* Fixes */}
      <CollapsibleSection
        title="Applied Fixes"
        count={report.fixes?.length ?? 0}
      >
        {report.fixes && report.fixes.length > 0 ? (
          <div className="space-y-4">
            {report.fixes.map((fix) => (
              <div key={fix.id} className="space-y-2">
                <p className="font-mono text-xs font-medium text-gray-700">{fix.file_path}</p>
                <DiffViewer original={fix.original} suggested={fix.suggested} />
                {fix.explanation && (
                  <div className="rounded-md bg-blue-50 border border-blue-100 px-3 py-2 text-sm text-blue-800">
                    <span className="font-medium">Explanation: </span>
                    {fix.explanation}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500 italic">No fixes recorded.</p>
        )}
      </CollapsibleSection>

      {/* Generated Tests */}
      <CollapsibleSection
        title="Generated Tests"
        count={report.tests_generated?.length ?? 0}
      >
        {report.tests_generated && report.tests_generated.length > 0 ? (
          <div className="space-y-4">
            {report.tests_generated.map((t) => (
              <CodeBlock key={t.file} code={t.code} filename={t.file} language="python" />
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500 italic">No tests generated.</p>
        )}
      </CollapsibleSection>

      {/* ── Action row ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 pt-2 flex-wrap">
        {/* New Analysis */}
        <button
          type="button"
          onClick={() => navigate('/analysis/new')}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 transition-colors"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          New Analysis
        </button>

        {/* Copy Report JSON */}
        <button
          type="button"
          onClick={handleCopyJson}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 transition-colors"
        >
          {copied ? (
            <>
              <svg className="h-4 w-4 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
              <span className="text-green-700">Copied!</span>
            </>
          ) : (
            <>
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5a3.375 3.375 0 00-3.375-3.375H9.75" />
              </svg>
              Copy Report JSON
            </>
          )}
        </button>
      </div>
    </div>
  )
}
