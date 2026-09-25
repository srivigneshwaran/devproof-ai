import { apiClient } from './client'
import type { RelevantFile, RootCause } from './analysisApi'
import type { Fix } from './fixApi'

// ---- Types (matching REST API contract) ------------------------------------

export type Verdict = 'PASS' | 'FAIL' | 'PARTIAL' | 'ERROR'

export interface GeneratedTest {
  file: string
  code: string
}

export interface VerificationReport {
  session_id: string
  project_name: string
  bug_description: string
  verdict: Verdict
  relevant_files: RelevantFile[]
  root_causes: RootCause[]
  fixes: Fix[]
  tests_generated: GeneratedTest[]
  test_output: string
  tests_passed: number
  tests_failed: number
  summary: string
  created_at: string
}

// ---- API calls -------------------------------------------------------------

/** GET /api/report/{session_id} — retrieve the verification report */
export async function getReport(session_id: string): Promise<VerificationReport> {
  const res = await apiClient.get<VerificationReport>(`/report/${session_id}`)
  return res.data
}
