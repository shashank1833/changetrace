import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { PrecisionDashboard } from '../components/PrecisionDashboard'
import { api } from '../lib/api'

describe('PrecisionDashboard Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders precision metrics and KPI cards on load', async () => {
    const mockMetrics = {
      total_feedback_count: 30,
      accepted_count: 24,
      rejected_count: 6,
      overall_precision: 0.8,
      precision_by_kind: {
        CONTRADICTION: {
          precision: 0.9,
          total: 10,
          accepted: 9,
          multiplier: 1.1,
          penalty: 0,
        },
      },
      precision_by_version: {},
      calibrations_active: 1,
    }

    const mockSummary = {
      rejection_reasons: { 'False positive': 4, 'Intentional': 2 },
      calibrated_penalties: {},
      calibrated_multipliers: { CONTRADICTION: 1.1 },
      rules: { CONTRADICTION: 'Promote confidence by 1.1x' },
    }

    vi.spyOn(api, 'feedbackMetrics').mockResolvedValue(mockMetrics)
    vi.spyOn(api, 'feedbackSummary').mockResolvedValue(mockSummary)

    render(<PrecisionDashboard />)

    expect(screen.getByText(/Precision & Feedback Dashboard/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText(/Empirical Precision/i)).toBeInTheDocument()
      expect(screen.getByText(/80%/)).toBeInTheDocument()
      expect(screen.getAllByText(/CONTRADICTION/).length).toBeGreaterThan(0)
      expect(screen.getByText(/Promote confidence by 1.1x/)).toBeInTheDocument()
    })
  })

  it('displays error message when API fails', async () => {
    vi.spyOn(api, 'feedbackMetrics').mockRejectedValue(new Error('Network error loading metrics'))
    vi.spyOn(api, 'feedbackSummary').mockRejectedValue(new Error('Network error loading summary'))

    render(<PrecisionDashboard />)

    await waitFor(() => {
      expect(screen.getByText(/Network error/i)).toBeInTheDocument()
    })
  })
})
