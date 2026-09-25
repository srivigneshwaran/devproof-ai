import { apiClient } from './client'
import type { VerificationReport } from './reportApi'

// ---- API calls -------------------------------------------------------------

/**
 * POST /api/verify — run the full verification pipeline for a session.
 * Requires the session to be in fix_approved status; returns HTTP 409 otherwise.
 * Orchestrates test generation, pytest execution, and report creation in one call.
 */
export async function runVerification(session_id: string): Promise<VerificationReport> {
  const res = await apiClient.post<VerificationReport>('/verify', { session_id })
  return res.data
}
