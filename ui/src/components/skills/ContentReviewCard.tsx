import React, { useCallback, useState } from 'react';

import {
  ArrowPathIcon,
  CheckIcon,
  ClockIcon,
  DocumentTextIcon,
  ExclamationTriangleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import type { ContentGateResult, ContentReview } from '../../types/skill';

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// The generated ContentReview type uses `{ [key: string]: unknown }` for nested objects.
// Define local shape interfaces for safe property access in JSX.
interface ClassificationShape {
  doc_type?: string;
  confidence?: string;
  reasoning?: string;
}
interface RelevanceShape {
  is_relevant?: boolean;
  reasoning?: string;
  applicable_namespaces?: string[];
}
interface PlacementShape {
  target_namespace?: string;
  target_filename?: string;
  merge_strategy?: string;
  reasoning?: string;
  merge_target?: string | null;
}
interface ValidationShape {
  valid?: boolean;
  errors?: string[];
  warnings?: string[];
}

const ContentGatesSection: React.FC<{ passed: boolean; checks: ContentGateResult[] }> = ({
  passed,
  checks,
}) => {
  const failedChecks = checks.filter((c) => !c.passed);
  const passedCount = checks.length - failedChecks.length;

  if (passed) {
    return (
      <div
        className="flex items-center gap-1.5 text-xs text-green-400 mb-3"
        data-testid="content-gates-passed"
      >
        <CheckIcon className="w-3.5 h-3.5" />
        Content gates passed ({passedCount}/{checks.length})
      </div>
    );
  }

  return (
    <details className="mb-3" data-testid="content-gates-failed">
      <summary className="flex items-center gap-1.5 text-xs text-red-400 cursor-pointer hover:text-red-300">
        <XMarkIcon className="w-3.5 h-3.5" />
        {passedCount}/{checks.length} content gates passed
      </summary>
      <div className="mt-2 space-y-1.5 pl-5">
        {failedChecks.map((check, i) => (
          <div key={i} className="text-xs">
            <span className="font-medium text-red-400">{check.check_name}</span>
            {check.errors && check.errors.length > 0 && (
              <ul className="mt-0.5 text-gray-400 list-disc pl-4">
                {check.errors.map((err, j) => (
                  <li key={j}>{err}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </details>
  );
};

interface ContentReviewCardProps {
  review: ContentReview;
  skillId: string;
  showActions?: boolean;
  onApproved?: () => void;
}

export const ContentReviewCard: React.FC<ContentReviewCardProps> = ({
  review,
  skillId,
  showActions = false,
  onApproved,
}) => {
  const { runSafe } = useErrorHandler('ContentReviewCard');
  const [status, setStatus] = useState(review.status);

  const handleApprove = useCallback(async () => {
    await runSafe(backendApi.applyContentReview(skillId, review.id), 'applyContentReview', {
      action: 'applying content review',
      entityId: review.id,
    });
    setStatus('applied');
    onApproved?.();
  }, [skillId, review.id, runSafe, onApproved]);

  const handleReject = useCallback(async () => {
    const reason = window.prompt('Reason for rejection:');
    if (reason === null) return;
    await runSafe(
      backendApi.rejectContentReview(skillId, review.id, { reason }),
      'rejectContentReview',
      { action: 'rejecting content review', entityId: review.id }
    );
    setStatus('rejected');
  }, [skillId, review.id, runSafe]);

  const handleRetry = useCallback(async () => {
    const [result] = await runSafe(
      backendApi.retryContentReview(skillId, review.id),
      'retryContentReview',
      { action: 'retrying content review', entityId: review.id }
    );
    if (result) {
      setStatus(result.status);
    }
  }, [skillId, review.id, runSafe]);

  const getStatusColor = (s: string) => {
    if (s === 'applied') return 'text-green-400';
    if (s === 'rejected') return 'text-red-400';
    if (s === 'failed') return 'text-red-400';
    if (s === 'flagged') return 'text-amber-400';
    if (s === 'completed' || s === 'approved') return 'text-blue-400';
    return 'text-yellow-400';
  };
  const statusColor = getStatusColor(status);

  const pipelineResult = review.pipeline_result as Record<string, unknown> | null | undefined;
  const classification = (pipelineResult?.classification as ClassificationShape) ?? null;
  const relevance = (pipelineResult?.relevance as RelevanceShape) ?? null;
  const placement = (pipelineResult?.placement as PlacementShape) ?? null;
  const validation = (pipelineResult?.validation as ValidationShape) ?? null;

  return (
    <div className="bg-dark-800 border border-gray-700/30 rounded-lg p-4">
      {/* Filename header */}
      {review.original_filename && (
        <div
          className="flex items-center gap-1.5 text-xs text-gray-500 mb-2"
          data-testid="review-filename"
        >
          <DocumentTextIcon className="w-3.5 h-3.5" />
          {review.original_filename}
        </div>
      )}

      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium uppercase ${statusColor}`}>{status}</span>
          {classification && (
            <span className="text-xs text-gray-500 bg-dark-700 px-1.5 py-0.5 rounded-sm">
              {classification.doc_type}
            </span>
          )}
          {classification?.confidence && (
            <span className="text-xs text-gray-500">{classification.confidence} confidence</span>
          )}
        </div>
        {showActions && status === 'failed' && (
          <div className="flex gap-2">
            <button
              onClick={() => void handleRetry()}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md text-white bg-yellow-600 hover:bg-yellow-700 transition-colors"
            >
              <ArrowPathIcon className="w-3.5 h-3.5" />
              Retry
            </button>
          </div>
        )}
        {status === 'flagged' && <span className="text-xs text-amber-400">Needs attention</span>}
        {showActions && status !== 'applied' && status !== 'rejected' && status !== 'failed' && (
          <div className="flex gap-2">
            <button
              onClick={() => void handleApprove()}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md text-white bg-green-600 hover:bg-green-700 transition-colors"
            >
              <CheckIcon className="w-3.5 h-3.5" />
              Approve
            </button>
            <button
              onClick={() => void handleReject()}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md text-white bg-red-600 hover:bg-red-700 transition-colors"
            >
              <XMarkIcon className="w-3.5 h-3.5" />
              Reject
            </button>
          </div>
        )}
      </div>

      {/* Content gates */}
      {review.content_gates_result && review.content_gates_result.length > 0 && (
        <ContentGatesSection
          passed={review.content_gates_passed}
          checks={review.content_gates_result}
        />
      )}

      {/* Error detail for failed reviews */}
      {status === 'failed' && review.error_message && (
        <div
          className="flex items-start gap-3 bg-red-900/20 border border-red-500/30 rounded-lg p-3 mb-3"
          data-testid="review-error"
        >
          <ExclamationTriangleIcon className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-xs font-medium text-red-400">{review.error_message}</p>
            {review.error_code && (
              <p className="text-xs text-gray-500 mt-0.5 font-mono">{review.error_code}</p>
            )}
          </div>
        </div>
      )}

      {/* Flagged review explanation */}
      {status === 'flagged' && (
        <div
          className="flex items-start gap-3 bg-amber-900/20 border border-amber-500/30 rounded-lg p-3 mb-3"
          data-testid="review-flagged"
        >
          <ExclamationTriangleIcon className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-xs text-amber-300">
            {!review.content_gates_passed
              ? 'This review was flagged because it did not pass all content gates. Review the details below before approving.'
              : 'This review was flagged for manual review. Check the summary and pipeline results below before approving.'}
          </p>
        </div>
      )}

      {review.summary && <p className="text-sm text-gray-300 mb-3">{review.summary}</p>}

      <div className="grid grid-cols-2 gap-3 text-xs mb-3">
        {placement && (
          <div className="bg-dark-900 rounded-md p-2">
            <span className="font-medium text-gray-400">Placement</span>
            <p className="text-gray-300 mt-0.5">
              {placement.target_namespace}
              {placement.target_filename}
            </p>
            <p className="text-gray-500 mt-0.5">Strategy: {placement.merge_strategy}</p>
          </div>
        )}
        {relevance && (
          <div className="bg-dark-900 rounded-md p-2">
            <span className="font-medium text-gray-400">Relevance</span>
            <p className="text-gray-300 mt-0.5">
              {relevance.is_relevant ? 'Relevant' : 'Not relevant'}
            </p>
            <p className="text-gray-500 mt-0.5">{relevance.reasoning}</p>
          </div>
        )}
      </div>

      {validation && validation.warnings && validation.warnings.length > 0 && (
        <div className="text-xs text-yellow-500 mb-2">
          {validation.warnings.map((w: string, i: number) => (
            <p key={i}>{w}</p>
          ))}
        </div>
      )}

      {/* Rejection reason */}
      {status === 'rejected' && review.rejection_reason && (
        <div
          className="flex items-start gap-3 bg-red-900/10 border border-red-500/20 rounded-lg p-3 mb-3"
          data-testid="review-rejection-reason"
        >
          <XMarkIcon className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-xs font-medium text-red-400">Rejection reason</p>
            <p className="text-xs text-gray-400 mt-0.5">{review.rejection_reason}</p>
          </div>
        </div>
      )}

      {review.transformed_content && (
        <details className="mt-3">
          <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-300">
            Preview content
          </summary>
          <pre className="mt-2 text-xs text-gray-300 bg-dark-900 rounded-md p-3 overflow-x-auto whitespace-pre-wrap font-mono">
            {review.transformed_content}
          </pre>
        </details>
      )}

      {/* Timestamps */}
      <div
        className="flex items-center gap-3 mt-3 pt-3 border-t border-gray-700/20"
        data-testid="review-timestamps"
      >
        <span className="inline-flex items-center gap-1 text-xs text-gray-600">
          <ClockIcon className="w-3 h-3" />
          {formatTimestamp(review.created_at)}
        </span>
        {review.completed_at && (
          <span className="text-xs text-gray-600">
            Completed {formatTimestamp(review.completed_at)}
          </span>
        )}
        {review.applied_at && (
          <span className="text-xs text-gray-600">
            Applied {formatTimestamp(review.applied_at)}
          </span>
        )}
      </div>
    </div>
  );
};
