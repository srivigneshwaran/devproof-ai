import { apiClient } from './client'

// ---- Types (matching REST API contract) ------------------------------------

export interface Fix {
  id: string
  file_path: string
  original: string
  suggested: string
  explanation: string
}

export interface FixList {
  session_id: string
  fixes: Fix[]
}

export interface ApproveBody {
  approved: boolean
  feedback?: string
}

export interface ApproveResult {
  status: 'fix_approved' | 'fix_rejected'
}

// ---- API calls -------------------------------------------------------------

/** POST /api/fix — generate fix suggestions for a session */
export async function generateFixes(session_id: string): Promise<FixList> {
  const res = await apiClient.post<FixList>('/fix', { session_id })
  return res.data
}

/** GET /api/fix/{session_id} — retrieve existing fix suggestions */
export async function getFixes(session_id: string): Promise<FixList> {
  const res = await apiClient.get<FixList>(`/fix/${session_id}`)
  return res.data
}

/**
 * POST /api/fix/{session_id}/approve — approve or reject the proposed fix.
 * Approval transitions session.status to fix_approved.
 * Rejection transitions to fix_rejected and stores optional feedback.
 */
export async function approveFix(
  session_id: string,
  approved: boolean,
  feedback?: string,
): Promise<ApproveResult> {
  const body: ApproveBody = { approved, ...(feedback !== undefined && { feedback }) }
  const res = await apiClient.post<ApproveResult>(`/fix/${session_id}/approve`, body)
  return res.data
}
