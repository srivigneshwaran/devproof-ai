import { apiClient } from './client'

// ---- Types (matching REST API contract) ------------------------------------

export type SessionStatus =
  | 'created'
  | 'analyzed'
  | 'fix_proposed'
  | 'fix_approved'
  | 'fix_rejected'
  | 'verified'

export interface SessionCreate {
  project_id: string
  bug_description: string
}

export interface Session {
  id: string
  project_id: string
  project_name: string
  bug_description: string
  status: SessionStatus
  created_at: string
}

// ---- API calls -------------------------------------------------------------

/** POST /api/sessions — create a new session */
export async function createSession(body: SessionCreate): Promise<Session> {
  const res = await apiClient.post<Session>('/sessions', body)
  return res.data
}

/** GET /api/sessions — list all sessions */
export async function listSessions(): Promise<Session[]> {
  const res = await apiClient.get<Session[]>('/sessions')
  return res.data
}

/** GET /api/sessions/{id} — get a single session by ID */
export async function getSession(id: string): Promise<Session> {
  const res = await apiClient.get<Session>(`/sessions/${id}`)
  return res.data
}
