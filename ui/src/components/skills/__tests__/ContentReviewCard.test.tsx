import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { ContentReview } from '../../../types/skill';
import { ContentReviewCard } from '../ContentReviewCard';

const mockReview: ContentReview = {
  id: 'rev-1',
  tenant_id: 'tenant-1',
  skill_id: 'skill-1',
  pipeline_name: 'extraction',
  pipeline_mode: 'review_transform',
  trigger_source: 'manual',
  document_id: 'doc-1',
  original_filename: 'test.md',
  content_gates_passed: true,
  content_gates_result: [],
  pipeline_result: {
    classification: { doc_type: 'procedure', reasoning: 'test', confidence: 'high' },
    relevance: { reasoning: 'relevant content', is_relevant: true, applicable_namespaces: [] },
    placement: {
      reasoning: 'best fit',
      merge_target: null,
      merge_strategy: 'replace',
      target_filename: 'new-section.md',
      target_namespace: 'docs/',
    },
    validation: { valid: true, errors: [], warnings: [] },
  },
  transformed_content: '# Extracted Content\nSome content here.',
  summary: 'Extracted a new investigation procedure.',
  status: 'pending',
  applied_document_id: null,
  rejection_reason: null,
  error_message: null,
  bypassed: false,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  completed_at: null,
  applied_at: null,
};

describe('ContentReviewCard', () => {
  it('renders review details', () => {
    render(<ContentReviewCard skillId="skill-1" review={mockReview} />);

    expect(screen.getByText('pending')).toBeInTheDocument();
    expect(screen.getByText('procedure')).toBeInTheDocument();
    expect(screen.getByText('Extracted a new investigation procedure.')).toBeInTheDocument();
  });

  it('hides action buttons by default', () => {
    render(<ContentReviewCard skillId="skill-1" review={mockReview} />);

    expect(screen.queryByText('Approve')).not.toBeInTheDocument();
    expect(screen.queryByText('Reject')).not.toBeInTheDocument();
    expect(screen.queryByText('Retry')).not.toBeInTheDocument();
  });

  it('shows action buttons when showActions is true', () => {
    render(<ContentReviewCard skillId="skill-1" review={mockReview} showActions />);

    expect(screen.getByText('Approve')).toBeInTheDocument();
    expect(screen.getByText('Reject')).toBeInTheDocument();
  });

  it('renders flagged status with amber color', () => {
    const flagged = { ...mockReview, status: 'flagged' as const };
    render(<ContentReviewCard skillId="skill-1" review={flagged} />);

    const statusEl = screen.getByText('flagged');
    expect(statusEl.className).toContain('text-amber-400');
  });

  it('shows preview toggle for transformed content', () => {
    render(<ContentReviewCard skillId="skill-1" review={mockReview} />);

    expect(screen.getByText('Preview content')).toBeInTheDocument();
  });

  it('shows content gates passed indicator', () => {
    const withContentGates = {
      ...mockReview,
      content_gates_result: [
        { check_name: 'schema_valid', passed: true, errors: [] },
        { check_name: 'no_duplicates', passed: true, errors: [] },
      ],
    };
    render(<ContentReviewCard skillId="skill-1" review={withContentGates} />);

    expect(screen.getByTestId('content-gates-passed')).toBeInTheDocument();
    expect(screen.getByText(/Content gates passed/)).toBeInTheDocument();
  });

  it('shows content gates failed with expandable details', () => {
    const withFailedGates = {
      ...mockReview,
      content_gates_passed: false,
      content_gates_result: [
        { check_name: 'schema_valid', passed: true, errors: [] },
        { check_name: 'no_duplicates', passed: false, errors: ['Duplicate entry found'] },
      ],
    };
    render(<ContentReviewCard skillId="skill-1" review={withFailedGates} />);

    expect(screen.getByTestId('content-gates-failed')).toBeInTheDocument();
    expect(screen.getByText('1/2 content gates passed')).toBeInTheDocument();
    expect(screen.getByText('no_duplicates')).toBeInTheDocument();
    expect(screen.getByText('Duplicate entry found')).toBeInTheDocument();
  });

  it('shows error message and error code for failed review', () => {
    const failed = {
      ...mockReview,
      status: 'failed' as const,
      error_message: 'Pipeline timed out after 120s',
      error_code: 'pipeline_timeout',
    };
    render(<ContentReviewCard skillId="skill-1" review={failed} />);

    expect(screen.getByTestId('review-error')).toBeInTheDocument();
    expect(screen.getByText('Pipeline timed out after 120s')).toBeInTheDocument();
    expect(screen.getByText('pipeline_timeout')).toBeInTheDocument();
  });

  it('does not show error block when failed but no error_message', () => {
    const failed = { ...mockReview, status: 'failed' as const, error_message: null };
    render(<ContentReviewCard skillId="skill-1" review={failed} />);

    expect(screen.queryByTestId('review-error')).not.toBeInTheDocument();
  });

  it('shows flagged explanation when content gates failed', () => {
    const flagged = {
      ...mockReview,
      status: 'flagged' as const,
      content_gates_passed: false,
      content_gates_result: [
        { check_name: 'relevance', passed: false, errors: ['Not relevant to skill'] },
      ],
    };
    render(<ContentReviewCard skillId="skill-1" review={flagged} />);

    expect(screen.getByTestId('review-flagged')).toBeInTheDocument();
    expect(screen.getByText(/did not pass all content gates/)).toBeInTheDocument();
  });

  it('shows generic flagged explanation when content gates passed', () => {
    const flagged = {
      ...mockReview,
      status: 'flagged' as const,
      content_gates_passed: true,
    };
    render(<ContentReviewCard skillId="skill-1" review={flagged} />);

    expect(screen.getByTestId('review-flagged')).toBeInTheDocument();
    expect(screen.getByText(/flagged for manual review/)).toBeInTheDocument();
  });

  it('shows original_filename when present', () => {
    render(<ContentReviewCard skillId="skill-1" review={mockReview} />);

    expect(screen.getByTestId('review-filename')).toBeInTheDocument();
    expect(screen.getByText('test.md')).toBeInTheDocument();
  });

  it('does not show filename when original_filename is null', () => {
    const noFile = { ...mockReview, original_filename: null };
    render(<ContentReviewCard skillId="skill-1" review={noFile} />);

    expect(screen.queryByTestId('review-filename')).not.toBeInTheDocument();
  });

  it('shows timestamps', () => {
    render(<ContentReviewCard skillId="skill-1" review={mockReview} />);

    expect(screen.getByTestId('review-timestamps')).toBeInTheDocument();
  });

  it('shows completed_at timestamp when present', () => {
    const completed = {
      ...mockReview,
      status: 'approved' as const,
      completed_at: '2025-01-02T12:00:00Z',
    };
    render(<ContentReviewCard skillId="skill-1" review={completed} />);

    expect(screen.getByText(/Completed/)).toBeInTheDocument();
  });

  it('shows applied_at timestamp when present', () => {
    const applied = {
      ...mockReview,
      status: 'applied' as const,
      applied_at: '2025-01-03T14:00:00Z',
    };
    render(<ContentReviewCard skillId="skill-1" review={applied} />);

    expect(screen.getByText(/Applied/)).toBeInTheDocument();
  });

  it('shows rejection reason for rejected review', () => {
    const rejected = {
      ...mockReview,
      status: 'rejected' as const,
      rejection_reason: 'Content is outdated and no longer accurate.',
    };
    render(<ContentReviewCard skillId="skill-1" review={rejected} />);

    expect(screen.getByTestId('review-rejection-reason')).toBeInTheDocument();
    expect(screen.getByText('Content is outdated and no longer accurate.')).toBeInTheDocument();
  });

  it('does not show rejection reason when absent', () => {
    const rejected = {
      ...mockReview,
      status: 'rejected' as const,
      rejection_reason: null,
    };
    render(<ContentReviewCard skillId="skill-1" review={rejected} />);

    expect(screen.queryByTestId('review-rejection-reason')).not.toBeInTheDocument();
  });
});
