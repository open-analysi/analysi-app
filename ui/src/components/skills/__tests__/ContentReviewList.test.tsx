import { render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import type { ContentReview } from '../../../types/skill';
import { ContentReviewList } from '../ContentReviewList';

// Hoisted mock state
const { storeState } = vi.hoisted(() => {
  const state = {
    contentReviews: [] as unknown[],
    reviewing: false,
  };
  return { storeState: state };
});

vi.mock('../../../store/skillStore', () => ({
  useSkillStore: () => ({
    contentReviews: storeState.contentReviews,
    setContentReviews: vi.fn(),
    reviewing: storeState.reviewing,
  }),
}));

vi.mock('../../../hooks/useErrorHandler', () => ({
  default: vi.fn(() => ({
    error: { hasError: false, message: '' },
    clearError: vi.fn(),
    handleError: vi.fn(),
    createContext: vi.fn(),
    runSafe: vi.fn(() => Promise.resolve([{ content_reviews: [] }, undefined])),
  })),
}));

vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getContentReviews: vi.fn().mockResolvedValue({ content_reviews: [] }),
  },
}));

// Mock ContentReviewCard to keep tests focused on the list/overview
vi.mock('../ContentReviewCard', () => ({
  ContentReviewCard: ({ review }: { review: ContentReview }) => (
    <div data-testid={`review-card-${review.id}`}>{review.original_filename}</div>
  ),
}));

function makeReview(overrides: Partial<ContentReview> & { id: string }): ContentReview {
  return {
    tenant_id: 'tenant-1',
    skill_id: 'skill-1',
    pipeline_name: 'extraction',
    pipeline_mode: 'review_transform',
    trigger_source: 'manual',
    document_id: 'doc-1',
    original_filename: 'document.md',
    content_gates_passed: true,
    content_gates_result: [],
    pipeline_result: null,
    transformed_content: null,
    summary: null,
    status: 'applied',
    applied_document_id: null,
    rejection_reason: null,
    error_message: null,
    bypassed: false,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    completed_at: null,
    applied_at: null,
    ...overrides,
  } as ContentReview;
}

describe('ContentReviewList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeState.contentReviews = [];
    storeState.reviewing = false;
  });

  it('shows empty state when no reviews', () => {
    render(<ContentReviewList skillId="skill-1" />);
    expect(screen.getByText(/No reviews yet/)).toBeInTheDocument();
  });

  it('does not show documents overview when no reviews', () => {
    render(<ContentReviewList skillId="skill-1" />);
    expect(screen.queryByTestId('documents-overview')).not.toBeInTheDocument();
  });

  describe('DocumentsOverview', () => {
    const multiFileReviews = [
      makeReview({ id: 'r1', original_filename: 'procedures.md', status: 'applied' }),
      makeReview({ id: 'r2', original_filename: 'playbook.md', status: 'applied' }),
      makeReview({ id: 'r3', original_filename: 'checklist.md', status: 'flagged' }),
      makeReview({ id: 'r4', original_filename: 'runbook.md', status: 'pending' }),
      makeReview({ id: 'r5', original_filename: 'guide.md', status: 'failed' }),
      makeReview({ id: 'r6', original_filename: 'notes.md', status: 'rejected' }),
      makeReview({ id: 'r7', original_filename: 'overview.md', status: 'approved' }),
    ];

    beforeEach(() => {
      storeState.contentReviews = multiFileReviews;
    });

    it('shows documents overview when reviews exist', () => {
      render(<ContentReviewList skillId="skill-1" />);
      expect(screen.getByTestId('documents-overview')).toBeInTheDocument();
      expect(screen.getByText('Documents Overview')).toBeInTheDocument();
    });

    it('shows status summary chips with correct counts', () => {
      render(<ContentReviewList skillId="skill-1" />);
      expect(screen.getByText('2 applied')).toBeInTheDocument();
      expect(screen.getByText('1 processing')).toBeInTheDocument();
      expect(screen.getByText('1 flagged')).toBeInTheDocument();
      expect(screen.getByText('1 failed')).toBeInTheDocument();
      expect(screen.getByText('1 rejected')).toBeInTheDocument();
      expect(screen.getByText('1 approved')).toBeInTheDocument();
    });

    it('lists all files with their status badges in the overview', () => {
      render(<ContentReviewList skillId="skill-1" />);
      const fileList = screen.getByTestId('documents-file-list');
      expect(fileList).toBeInTheDocument();

      // All 7 files should appear in the overview file list
      const fileListItems = fileList.querySelectorAll('.flex.items-center');
      expect(fileListItems).toHaveLength(7);
    });

    it('shows status labels next to files in the overview', () => {
      render(<ContentReviewList skillId="skill-1" />);
      const fileList = screen.getByTestId('documents-file-list');
      // Status badges appear as text within the file list
      expect(within(fileList).getAllByText('Applied')).toHaveLength(2);
      expect(within(fileList).getByText('Flagged')).toBeInTheDocument();
      expect(within(fileList).getByText('Pending')).toBeInTheDocument();
      expect(within(fileList).getByText('Failed')).toBeInTheDocument();
      expect(within(fileList).getByText('Rejected')).toBeInTheDocument();
      expect(within(fileList).getAllByText('Approved')).toHaveLength(1);
    });

    it('shows "Untitled document" for reviews without filename', () => {
      storeState.contentReviews = [
        makeReview({ id: 'r1', original_filename: null, status: 'applied' }),
      ];
      render(<ContentReviewList skillId="skill-1" />);
      const fileList = screen.getByTestId('documents-file-list');
      expect(within(fileList).getByText('Untitled document')).toBeInTheDocument();
    });

    it('only shows non-zero status chips', () => {
      storeState.contentReviews = [
        makeReview({ id: 'r1', original_filename: 'a.md', status: 'applied' }),
        makeReview({ id: 'r2', original_filename: 'b.md', status: 'applied' }),
      ];
      render(<ContentReviewList skillId="skill-1" />);
      const summary = screen.getByTestId('status-summary');
      expect(within(summary).getByText('2 applied')).toBeInTheDocument();
      expect(within(summary).queryByText(/processing/)).not.toBeInTheDocument();
      expect(within(summary).queryByText(/flagged/)).not.toBeInTheDocument();
      expect(within(summary).queryByText(/failed/)).not.toBeInTheDocument();
      expect(within(summary).queryByText(/approved/)).not.toBeInTheDocument();
    });

    it('shows review count header', () => {
      render(<ContentReviewList skillId="skill-1" />);
      expect(screen.getByText('Reviews (7)')).toBeInTheDocument();
    });
  });
});
