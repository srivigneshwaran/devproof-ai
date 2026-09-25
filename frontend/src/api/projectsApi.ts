import { apiClient } from './client'

// ---- Types (matching REST API contract) ------------------------------------

export interface Project {
  id: string
  name: string
  description: string
  file_count: number
}

export interface ProjectFile {
  path: string
  description: string
}

export interface UploadResult {
  session_file_paths: string[]
}

// ---- API calls -------------------------------------------------------------

/** GET /api/projects — list all available sample projects */
export async function listProjects(): Promise<Project[]> {
  const res = await apiClient.get<Project[]>('/projects')
  return res.data
}

/** GET /api/projects/{id}/files — list files for a specific project */
export async function getProjectFiles(id: string): Promise<ProjectFile[]> {
  const res = await apiClient.get<ProjectFile[]>(`/projects/${id}/files`)
  return res.data
}

/** POST /api/projects/upload — upload .py files for an ad-hoc session */
export async function uploadFiles(files: File[]): Promise<UploadResult> {
  const form = new FormData()
  files.forEach((f) => form.append('files[]', f))
  const res = await apiClient.post<UploadResult>('/projects/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}
