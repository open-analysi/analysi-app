import React, { useState } from 'react';

import { PencilIcon, TrashIcon } from '@heroicons/react/24/outline';

import type { TaskFeedback, TaskFeedbackUpdate } from '../../types/taskFeedback';
import ConfirmDialog from '../common/ConfirmDialog';
import UserDisplayName from '../common/UserDisplayName';

function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

interface TaskFeedbackItemProps {
  item: TaskFeedback;
  currentUserId: string | undefined;
  onUpdate: (feedbackId: string, data: TaskFeedbackUpdate) => Promise<void>;
  onDelete: (feedbackId: string) => Promise<void>;
}

const TaskFeedbackItem: React.FC<TaskFeedbackItemProps> = ({
  item,
  currentUserId,
  onUpdate,
  onDelete,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(item.feedback);
  const [isExpanded, setIsExpanded] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const isOwner = currentUserId === item.created_by;
  const isLong = item.feedback.length > 150;

  const handleSave = async () => {
    if (!editText.trim() || editText.trim() === item.feedback) {
      setIsEditing(false);
      setEditText(item.feedback);
      return;
    }
    setIsSaving(true);
    try {
      await onUpdate(item.id, { feedback: editText.trim() });
      setIsEditing(false);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    setShowDeleteConfirm(false);
    await onDelete(item.id);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditText(item.feedback);
  };

  return (
    <div className="group bg-dark-700 rounded-md px-2.5 py-2">
      {/* Header: author + time + actions */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-[11px] text-gray-500 truncate">
            <UserDisplayName userId={item.created_by} />
          </span>
          <span className="text-[11px] text-gray-600">{timeAgo(item.created_at)}</span>
        </div>
        {isOwner && !isEditing && (
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={() => setIsEditing(true)}
              className="p-0.5 text-gray-500 hover:text-gray-300 transition-colors"
              title="Edit feedback"
            >
              <PencilIcon className="w-3 h-3" />
            </button>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="p-0.5 text-gray-500 hover:text-red-400 transition-colors"
              title="Delete feedback"
            >
              <TrashIcon className="w-3 h-3" />
            </button>
          </div>
        )}
      </div>

      {/* Body: title + text or edit form */}
      {isEditing ? (
        <div>
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            className="w-full bg-dark-900 border border-gray-700 rounded-md text-xs text-gray-100 p-1.5 resize-none focus:outline-none focus:border-primary"
            rows={3}
          />
          <div className="flex justify-end gap-2 mt-1.5">
            <button
              onClick={handleCancelEdit}
              className="text-gray-400 text-xs hover:text-gray-200 transition-colors"
              disabled={isSaving}
            >
              Cancel
            </button>
            <button
              onClick={() => void handleSave()}
              disabled={isSaving || !editText.trim()}
              className="bg-primary text-white text-xs px-3 py-1 rounded-sm hover:bg-primary-dark transition-colors disabled:opacity-50"
            >
              {isSaving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
      ) : (
        <div>
          {item.title && <p className="text-xs font-medium text-gray-200 mb-0.5">{item.title}</p>}
          <p
            className={`text-xs text-gray-300 whitespace-pre-wrap ${
              !isExpanded && isLong ? 'line-clamp-3' : ''
            }`}
          >
            {item.feedback}
          </p>
          {isLong && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="text-[11px] text-primary hover:text-primary-light mt-0.5"
            >
              {isExpanded ? 'show less' : 'show more'}
            </button>
          )}
        </div>
      )}

      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={() => void handleDelete()}
        title="Delete Feedback?"
        message="This feedback will be permanently removed."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="warning"
      />
    </div>
  );
};

export default TaskFeedbackItem;
