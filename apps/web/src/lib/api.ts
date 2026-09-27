import type { Analysis, Repository } from '../types'

const API = import.meta.env.VITE_API_URL ?? ''
const headers = { 'Content-Type': 'application/json' }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...init, credentials: 'include', headers: { ...headers, ...init?.headers } })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: `Request failed: ${response.status}` }))
    throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail))
  }
  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as unknown as T
  }
  return response.json() as Promise<T>
}

export const api = {
  loginUrl: `${API}/api/v1/auth/github/login`,
  me: () => request<{ user_id: string; organization_id: string; role: string; email?: string }>('/api/v1/auth/me'),
  logout: () => request<void>('/api/v1/auth/logout', { method: 'POST' }),
  repositories: () => request<Repository[]>('/api/v1/repositories'),
  createRepository: (body: { name: string; source_path?: string; github_url?: string }) =>
    request<Repository>('/api/v1/repositories', { method: 'POST', body: JSON.stringify(body) }),
  syncRepository: (id: string) =>
    request<{ snapshot_id: string; commit_sha: string; status: string }>(`/api/v1/repositories/${id}/sync`, { method: 'POST' }),
  createChange: (body: { repository_id: string; description: string; proposed_diff?: string }) =>
    request<{ id: string }>('/api/v1/changes', { method: 'POST', body: JSON.stringify(body) }),
  analyze: (id: string) => request<{ id: string }>(`/api/v1/changes/${id}/analyze`, { method: 'POST' }),
  job: (id: string) => request<{ status: string; progress: number; analysis_id?: string; error?: string }>(`/api/v1/jobs/${id}`),
  analysis: (id: string) => request<Analysis>(`/api/v1/analyses/${id}`),
  feedback: (analysisId: string, findingId: string, decision: string) => request(
    `/api/v1/analyses/${analysisId}/findings/${findingId}/feedback`,
    { method: 'POST', body: JSON.stringify({ decision }) },
  ),
  report: (analysisId: string, format: 'json' | 'markdown') =>
    request<Analysis | { format: string; content: string }>(`/api/v1/analyses/${analysisId}/report?format=${format}`),
  feedbackMetrics: () =>
    request<{
      total_feedback_count: number
      accepted_count: number
      rejected_count: number
      overall_precision: number
      precision_by_kind: Record<string, { precision: number; total: number; accepted: number; multiplier: number; penalty: number }>
      precision_by_version: Record<string, { precision: number; total: number; accepted: number }>
      calibrations_active: number
    }>('/api/v1/feedback/metrics'),
  feedbackSummary: () =>
    request<{
      rejection_reasons: Record<string, number>
      calibrated_penalties: Record<string, number>
      calibrated_multipliers: Record<string, number>
      rules: Record<string, string>
    }>('/api/v1/feedback/summary'),
}
