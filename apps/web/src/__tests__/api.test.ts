import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from '../lib/api'

describe('ChangeTrace API Client', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches feedback metrics successfully', async () => {
    const mockMetrics = {
      total_feedback_count: 20,
      accepted_count: 17,
      rejected_count: 3,
      overall_precision: 0.85,
      precision_by_kind: {
        authorization: { precision: 0.9, total: 10, accepted: 9, multiplier: 1.0, penalty: 0 },
      },
      precision_by_version: {},
      calibrations_active: 3,
    }

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockMetrics), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )

    const result = await api.feedbackMetrics()
    expect(result.overall_precision).toBe(0.85)
    expect(result.total_feedback_count).toBe(20)
    expect(result.precision_by_kind.authorization.precision).toBe(0.9)
  })

  it('fetches feedback summary successfully', async () => {
    const mockSummary = {
      rejection_reasons: { 'False positive': 3 },
      calibrated_penalties: {},
      calibrated_multipliers: { authorization: 1.15 },
      rules: { authorization: 'Calibrated rule' },
    }

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockSummary), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )

    const result = await api.feedbackSummary()
    expect(result.rejection_reasons['False positive']).toBe(3)
    expect(result.calibrated_multipliers.authorization).toBe(1.15)
  })

  it('propagates HTTP error when API returns non-200', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Analysis not found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      })
    )

    await expect(api.analysis('non-existent-id')).rejects.toThrow('Analysis not found')
  })

  it('submits finding feedback with correct payload', async () => {
    let capturedBody: string | undefined
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(async (_url, init) => {
      capturedBody = init?.body as string
      return new Response(JSON.stringify({ status: 'recorded' }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      })
    })

    await api.feedback('analysis-123', 'finding-456', 'ACCEPTED')
    expect(capturedBody).toBeDefined()
    const parsed = JSON.parse(capturedBody!)
    expect(parsed.decision).toBe('ACCEPTED')
  })

  it('handles current user authentication endpoint', async () => {
    const mockUser = {
      user_id: 'usr-123',
      organization_id: 'org-456',
      role: 'OWNER',
      email: 'dev@changetrace.io',
    }

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockUser), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )

    const user = await api.me()
    expect(user.email).toBe('dev@changetrace.io')
    expect(user.role).toBe('OWNER')
  })

  it('throws error when current user endpoint returns 401', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      })
    )

    await expect(api.me()).rejects.toThrow('Unauthorized')
  })
})
