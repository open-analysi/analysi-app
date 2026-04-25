import React, { useCallback, useEffect, useState } from 'react';

import { PlusIcon, MinusIcon } from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { useUserCacheStore } from '../../store/userCacheStore';
import type { TaskFeedback } from '../../types/taskFeedback';

import TaskFeedbackItem from './TaskFeedbackItem';

interface TaskFeedbackSectionProps {
  taskId: string;
}

const TaskFeedbackSection: React.FC<TaskFeedbackSectionProps> = ({ taskId }) => {
  const [feedbacks, setFeedbacks] = useState<TaskFeedback[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [newFeedback, setNewFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const currentUser = useUserCacheStore((s) => s.currentUser);
  const fetchCurrentUser = useUserCacheStore((s) => s.fetchCurrentUser);
  const { runSafe } = useErrorHandler('TaskFeedbackSection');

  const fetchFeedback = useCallback(async () => {
    setIsLoading(true);
    try {
      const [result] = await runSafe(backendApi.getTaskFeedback(taskId), 'fetchFeedback', {
        action: 'fetching feedback',
        entityId: taskId,
      });
      if (result) {
        setFeedbacks(result.feedbacks);
      }
    } finally {
      setIsLoading(false);
    }
  }, [taskId, runSafe]);

  useEffect(() => {
    void fetchFeedback();
  }, [fetchFeedback]);

  useEffect(() => {
    if (!currentUser) {
      void fetchCurrentUser();
    }
  }, [currentUser, fetchCurrentUser]);

  const handleSubmit = async () => {
    if (!newFeedback.trim()) return;
    setIsSubmitting(true);
    try {
      const [created] = await runSafe(
        backendApi.createTaskFeedback(taskId, { feedback: newFeedback.trim() }),
        'createFeedback',
        { action: 'creating feedback', entityId: taskId }
      );
      if (created) {
        setFeedbacks((prev) => [created, ...prev]);
        setNewFeedback('');
        setShowForm(false);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpdate = async (feedbackId: string, data: { feedback?: string | null }) => {
    const [updated] = await runSafe(
      backendApi.updateTaskFeedback(taskId, feedbackId, data),
      'updateFeedback',
      { action: 'updating feedback', entityId: feedbackId }
    );
    if (updated) {
      setFeedbacks((prev) => prev.map((f) => (f.id === feedbackId ? updated : f)));
    }
  };

  const handleDelete = async (feedbackId: string) => {
    const [, error] = await runSafe(
      backendApi.deleteTaskFeedback(taskId, feedbackId),
      'deleteFeedback',
      { action: 'deleting feedback', entityId: feedbackId }
    );
    if (!error) {
      setFeedbacks((prev) => prev.filter((f) => f.id !== feedbackId));
    }
  };

  const handleCancel = () => {
    setShowForm(false);
    setNewFeedback('');
  };

  const enabledFeedbacks = feedbacks.filter((f) => f.status === 'enabled');

  return (
    <div>
      {/* Section header */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-medium text-gray-400 uppercase">
          Feedback
          {isLoading && <span className="ml-2 text-gray-500">...</span>}
          {!isLoading && enabledFeedbacks.length > 0 && (
            <span className="ml-1.5 text-gray-500">({enabledFeedbacks.length})</span>
          )}
        </h3>
        <button
          onClick={() => setShowForm(!showForm)}
          className="p-0.5 text-gray-400 hover:text-white transition-colors"
          title={showForm ? 'Cancel' : 'Add feedback'}
        >
          {showForm ? <MinusIcon className="w-3.5 h-3.5" /> : <PlusIcon className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Inline create form */}
      {showForm && (
        <div className="mb-2">
          <textarea
            value={newFeedback}
            onChange={(e) => setNewFeedback(e.target.value)}
            placeholder="Share feedback on this task..."
            className="w-full bg-dark-900 border border-gray-700 rounded-md text-xs text-gray-100 p-2 resize-none focus:outline-none focus:border-primary placeholder:text-gray-600"
            rows={3}
          />
          <div className="flex justify-end gap-2 mt-1.5">
            <button
              onClick={handleCancel}
              className="text-gray-400 text-xs hover:text-gray-200 transition-colors"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              onClick={() => void handleSubmit()}
              disabled={isSubmitting || !newFeedback.trim()}
              className="bg-primary text-white text-xs px-3 py-1 rounded-sm hover:bg-primary-dark transition-colors disabled:opacity-50"
            >
              {isSubmitting ? 'Submitting...' : 'Submit'}
            </button>
          </div>
        </div>
      )}

      {/* Feedback list */}
      {enabledFeedbacks.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          {enabledFeedbacks.map((item) => (
            <TaskFeedbackItem
              key={item.id}
              item={item}
              currentUserId={currentUser?.id}
              onUpdate={handleUpdate}
              onDelete={handleDelete}
            />
          ))}
        </div>
      ) : (
        !isLoading && <p className="text-xs text-gray-500">No feedback yet</p>
      )}
    </div>
  );
};

export default TaskFeedbackSection;
