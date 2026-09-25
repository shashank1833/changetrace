import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EvidenceDrawer } from '../components/EvidenceDrawer'
import type { Evidence } from '../types'

describe('EvidenceDrawer Component', () => {
  const mockEvidence: Evidence = {
    id: 'ev-1',
    repository_id: 'repo-abc',
    repository_snapshot_id: 'snap-123',
    commit_sha: 'a1b2c3d4e5f6',
    type: 'STATE_TRANSITION',
    location: {
      file: 'backend/services/billing.py',
      line_start: 42,
      line_end: 55,
      symbol: 'cancel_subscription',
    },
    snippet: 'def cancel_subscription():\n    pass',
    content_hash: 'sha256-hash-value',
    status: 'VALID',
    reason: 'Modifies subscription state to CANCELLED',
    strength: 'CONFIRMED',
    quality_score: 0.95,
  }

  it('renders nothing when evidence is undefined', () => {
    const { container } = render(<EvidenceDrawer evidence={undefined} onClose={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders evidence details and metadata correctly', () => {
    render(<EvidenceDrawer evidence={mockEvidence} onClose={() => {}} />)

    expect(screen.getByRole('complementary', { name: /evidence viewer/i })).toBeInTheDocument()
    expect(screen.getByText('backend/services/billing.py')).toBeInTheDocument()
    expect(screen.getByText(/Lines 42/)).toBeInTheDocument()
    expect(screen.getAllByText(/cancel_subscription/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Quality 95%/)).toBeInTheDocument()
    expect(screen.getByText(/CONFIRMED/)).toBeInTheDocument()
    expect(screen.getByText(/Modifies subscription state/)).toBeInTheDocument()
    expect(screen.getByText('a1b2c3d4e5f6')).toBeInTheDocument()
    expect(screen.getByText('sha256-hash-value')).toBeInTheDocument()
  })

  it('triggers onClose when close button is clicked', () => {
    const handleClose = vi.fn()
    render(<EvidenceDrawer evidence={mockEvidence} onClose={handleClose} />)

    const closeButton = screen.getByRole('button', { name: /close evidence/i })
    fireEvent.click(closeButton)
    expect(handleClose).toHaveBeenCalledTimes(1)
  })
})
