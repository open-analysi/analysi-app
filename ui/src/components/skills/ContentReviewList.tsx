import React, { useCallback, useEffect, useRef } from 'react';

import {
  CheckCircleIcon,
  DocumentTextIcon,
  ExclamationTriangleIcon,
  SparklesIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { useSkillStore } from '../../store/skillStore';
import type { ContentReview } from '../../types/skill';

import { ContentReviewCard } from './ContentReviewCard';

const POLL_INTERVAL = 10_000; // 10 seconds
const PENDING_STATUSES = new Set(['pending', 'processing', 'queued']);

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  flagged: { label: 'Flagged', color: 'text-amber-400', bg: 'bg-amber-400/10' },
  failed: { label: 'Failed', color: 'text-red-400', bg: 'bg-red-400/10' },
  pending: { label: 'Pending', color: 'text-yellow-400', bg: 'bg-yellow-400/10' },
  approved: { label: 'Approved', color: 'text-blue-400', bg: 'bg-blue-400/10' },
  applied: { label: 'Applied', color: 'text-green-400', bg: 'bg-green-400/10' },
  rejected: { label: 'Rejected', color: 'text-red-400', bg: 'bg-red-400/10' },
};

const DocumentsOverview: React.FC<{ reviews: ContentReview[] }> = ({ reviews }) => {
  if (reviews.length === 0) return null;

  const counts = reviews.reduce(
    (acc, r) => {
      if (r.status === 'applied') acc.applied++;
      else if (r.status === 'flagged') acc.flagged++;
      else if (r.status === 'failed') acc.failed++;
      else if (PENDING_STATUSES.has(r.status)) acc.pending++;
      else if (r.status === 'rejected') acc.rejected++;
      else if (r.status === 'approved') acc.approved++;
      return acc;
    },
    { applied: 0, flagged: 0, failed: 0, pending: 0, rejected: 0, approved: 0 }
  );

  return (
    <div
      className="bg-dark-800 border border-gray-700/30 rounded-lg p-4 mb-4"
      data-testid="documents-overview"
    >
      <h4 className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">
        Documents Overview
      </h4>

      {/* Status summary chips */}
      <div className="flex flex-wrap gap-2 mb-3" data-testid="status-summary">
        {counts.applied > 0 && (
          <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-green-400/10 text-green-400">
            <CheckCircleIcon className="w-3.5 h-3.5" />
            {counts.applied} applied
          </span>
        )}
        {counts.pending > 0 && (
          <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-yellow-400/10 text-yellow-400">
            <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
            {counts.pending} processing
          </span>
        )}
        {counts.flagged > 0 && (
          <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-amber-400/10 text-amber-400">
            <ExclamationTriangleIcon className="w-3.5 h-3.5" />
            {counts.flagged} flagged
          </span>
        )}
        {counts.failed > 0 && (
          <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-red-400/10 text-red-400">
            <XCircleIcon className="w-3.5 h-3.5" />
            {counts.failed} failed
          </span>
        )}
        {counts.approved > 0 && (
          <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-blue-400/10 text-blue-400">
            {counts.approved} approved
          </span>
        )}
        {counts.rejected > 0 && (
          <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-red-400/10 text-red-400">
            {counts.rejected} rejected
          </span>
        )}
      </div>

      {/* Compact file list */}
      <div className="space-y-1" data-testid="documents-file-list">
        {reviews.map((review) => {
          const cfg = STATUS_CONFIG[review.status] ?? {
            label: review.status,
            color: 'text-gray-400',
            bg: 'bg-gray-400/10',
          };
          return (
            <div
              key={review.id}
              className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-dark-700/50 text-xs"
            >
              <DocumentTextIcon className="w-3.5 h-3.5 text-gray-500 shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <span className="text-gray-300 truncate block">
                  {review.original_filename ?? 'Untitled document'}
                </span>
                {review.summary && (
                  <span className="text-gray-500 truncate block text-[11px] mt-0.5">
                    {review.summary}
                  </span>
                )}
              </div>
              <span
                className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium shrink-0 ${cfg.color} ${cfg.bg}`}
              >
                {cfg.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

interface ContentReviewListProps {
  skillId: string;
}

export const ContentReviewList: React.FC<ContentReviewListProps> = ({ skillId }) => {
  const { runSafe } = useErrorHandler('ContentReviewList');
  const { contentReviews, setContentReviews, reviewing } = useSkillStore();
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchReviews = useCallback(async () => {
    const [result] = await runSafe(backendApi.getContentReviews(skillId), 'fetchContentReviews', {
      action: 'fetching content reviews',
      entityId: skillId,
    });
    if (result) {
      setContentReviews(result.content_reviews || []);
    }
  }, [skillId, runSafe, setContentReviews]);

  // Initial fetch
  useEffect(() => {
    void fetchReviews();
  }, [fetchReviews]);

  // Poll while there are pending reviews or an active review is in progress
  const hasPending = reviewing || contentReviews.some((r) => PENDING_STATUSES.has(r.status));

  useEffect(() => {
    if (hasPending) {
      pollRef.current = setInterval(() => void fetchReviews(), POLL_INTERVAL);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [hasPending, fetchReviews]);

  return (
    <div className="space-y-4">
      {(reviewing || hasPending) && (
        <div className="flex items-center gap-3 bg-dark-800 border border-yellow-500/30 rounded-lg p-4">
          <div className="w-5 h-5 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin shrink-0" />
          <div>
            <p className="text-sm font-medium text-yellow-400">Review in progress</p>
            <p className="text-xs text-gray-400 mt-0.5">
              Processing documents. This may take several minutes. This page auto-refreshes every 10
              seconds.
            </p>
          </div>
        </div>
      )}

      {contentReviews.length > 0 && <DocumentsOverview reviews={contentReviews} />}

      {contentReviews.length > 0 && (
        <h3 className="text-sm font-medium text-gray-300">Reviews ({contentReviews.length})</h3>
      )}

      {contentReviews.length === 0 && !reviewing && !hasPending && (
        <div className="flex flex-col items-center justify-center h-64 text-gray-500 text-sm">
          <SparklesIcon className="w-8 h-8 mb-3 text-gray-600" />
          No reviews yet. Stage documents and run a review from the Onboarding tab.
        </div>
      )}

      {[...contentReviews]
        .sort((a, b) => {
          const priority: Record<string, number> = {
            flagged: 0,
            failed: 1,
            pending: 2,
            approved: 3,
            applied: 4,
            rejected: 5,
          };
          return (priority[a.status] ?? 3) - (priority[b.status] ?? 3);
        })
        .map((review) => (
          <ContentReviewCard key={review.id} review={review} skillId={skillId} />
        ))}
    </div>
  );
};
