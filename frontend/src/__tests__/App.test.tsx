import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import App from '../App'

describe('App Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      const urlStr = String(url)
      if (urlStr.includes('/api/v1/auth/me')) {
        return new Response(
          JSON.stringify({
            user_id: 'usr-1',
            organization_id: 'org-1',
            role: 'ADMIN',
            email: 'alex@company.com',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      }
      if (urlStr.includes('/api/v1/repositories')) {
        return new Response(
          JSON.stringify([
            {
              id: 'repo-1',
              name: 'Demo Repo',
              source_path: 'tests/evaluation/demo_repository',
              organization_id: 'org-1',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
          ]),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      }
      if (urlStr.includes('/api/v1/feedback/metrics')) {
        return new Response(
          JSON.stringify({
            total_feedback_count: 5,
            accepted_count: 4,
            rejected_count: 1,
            overall_precision: 0.8,
            precision_by_kind: {},
            precision_by_version: {},
            calibrations_active: 0,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      }
      if (urlStr.includes('/api/v1/feedback/summary')) {
        return new Response(
          JSON.stringify({
            rejection_reasons: {},
            calibrated_penalties: {},
            calibrated_multipliers: {},
            rules: {},
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      }
      return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
  })

  it('renders application header and authenticated user', async () => {
    render(<App />)

    expect(screen.getByText('ChangeTrace')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('alex@company.com')).toBeInTheDocument()
      expect(screen.getByText('Sign out')).toBeInTheDocument()
    })
  })

  it('allows switching to Precision & Feedback tab', async () => {
    render(<App />)

    const precisionTab = screen.getByRole('button', { name: /precision/i })
    fireEvent.click(precisionTab)

    await waitFor(() => {
      expect(screen.getByText(/Precision & Feedback Dashboard/i)).toBeInTheDocument()
    })
  })
})
