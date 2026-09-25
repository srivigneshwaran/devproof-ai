import { apiClient } from './client'

// ---- Types (matching REST API contract) ------------------------------------

export interface RelevantFile {
  path: string
  confidence: number
  reason: string
}

export interface RootCause {
  description: string
  file: string
  line_hint: number
}

export interface AnalysisResult {
  session_id: string
  relevant_files: RelevantFile[]
  root_causes: RootCause[]
}

// ---- API calls -------------------------------------------------------------

/** POST /api/analysis — trigger analysis for a session */
export async function runAnalysis(session_id: string): Promise<AnalysisResult> {
  const res = await apiClient.post<AnalysisResult>('/analysis', { session_id })
  return res.data
}

/** GET /api/analysis/{session_id} — retrieve existing analysis result */
export async function getAnalysis(session_id: string): Promise<AnalysisResult> {
  const res = await apiClient.get<AnalysisResult>(`/analysis/${session_id}`)
  return res.data
}
