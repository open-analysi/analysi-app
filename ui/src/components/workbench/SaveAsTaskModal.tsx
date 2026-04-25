import React, { useState, useEffect } from 'react';

import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react';
import { XMarkIcon, ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { extractApiErrorMessage } from '../../services/apiClient';
import { backendApi } from '../../services/backendApi';
import { Task } from '../../types/knowledge';
import { ConfirmDialog } from '../common/ConfirmDialog';

interface SaveAsTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (newTask: Task) => void;
  initialScript: string;
  initialName?: string;
  initialDescription?: string;
}

export const SaveAsTaskModal: React.FC<SaveAsTaskModalProps> = ({
  isOpen,
  onClose,
  onSave,
  initialScript,
  initialName = '',
  initialDescription = '',
}) => {
  const { runSafe } = useErrorHandler('SaveAsTaskModal');

  // Form state
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | undefined>(undefined);
  const [showScriptPreview, setShowScriptPreview] = useState(false);

  // Confirmation dialog state
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);

  // Reset form when modal opens, using initial values if provided
  useEffect(() => {
    if (isOpen) {
      setName(initialName);
      setDescription(initialDescription);
      setSaveError(undefined);
      setShowScriptPreview(false);
      setShowDiscardConfirm(false);
    }
  }, [isOpen, initialName, initialDescription]);

  // Handle escape key with unsaved changes warning
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' || event.key === 'Esc') {
        event.preventDefault();
        event.stopPropagation();

        // Check for unsaved changes directly in the handler
        // User has made changes if name or description differs from initial values
        const hasChanges = name !== initialName || description !== initialDescription;

        if (hasChanges) {
          setShowDiscardConfirm(true);
        } else {
          onClose();
        }
      }
    };

    document.addEventListener('keydown', handleEscape, true);
    return () => document.removeEventListener('keydown', handleEscape, true);
  }, [name, description, initialName, initialDescription, onClose]);

  const handleSave = async () => {
    if (!name.trim()) {
      setSaveError('Task name is required');
      return;
    }

    setIsLoading(true);
    setSaveError(undefined);

    try {
      const [response, apiError] = await runSafe(
        backendApi.createTask({
          name: name.trim(),
          description: description.trim(),
          script: initialScript,
        }),
        'createTask',
        {
          action: 'creating new task',
        }
      );

      if (apiError) {
        setSaveError(extractApiErrorMessage(apiError, 'Failed to create task'));
        return;
      }

      if (response) {
        // The response is already the Task from backendApi
        onSave(response as unknown as Task);
        onClose();
      } else {
        setSaveError('Invalid response from server');
      }
    } catch (error_) {
      setSaveError((error_ as Error).message || 'An unexpected error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSafeClose = () => {
    // User has made changes if name or description differs from initial values
    const hasChanges = name !== initialName || description !== initialDescription;

    if (hasChanges) {
      setShowDiscardConfirm(true);
    } else {
      onClose();
    }
  };

  const handleConfirmDiscard = () => {
    setShowDiscardConfirm(false);
    onClose();
  };

  return (
    <>
      <Dialog open={isOpen} onClose={handleSafeClose} className="relative z-50">
        <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

        <div className="fixed inset-0 flex items-center justify-center p-4">
          <DialogPanel className="mx-auto rounded-xl bg-white dark:bg-gray-800 p-6 w-full max-w-xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <DialogTitle className="text-lg font-medium text-gray-900 dark:text-gray-100">
                Save As New Task
              </DialogTitle>
              <button onClick={handleSafeClose} className="text-gray-400 hover:text-gray-500">
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <div className="space-y-4 flex-1 overflow-y-auto min-h-0">
              {/* Error message */}
              {saveError && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-3">
                  <div className="flex items-start">
                    <svg
                      className="h-5 w-5 text-red-400 mt-0.5 mr-2"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    <div className="flex-1">
                      <h3 className="text-sm font-medium text-red-800 dark:text-red-200">
                        Save Failed
                      </h3>
                      <p className="mt-1 text-sm text-red-700 dark:text-red-300">{saveError}</p>
                    </div>
                    <button
                      onClick={() => setSaveError(undefined)}
                      className="ml-3 text-red-400 hover:text-red-600"
                    >
                      <XMarkIcon className="h-5 w-5" />
                    </button>
                  </div>
                </div>
              )}

              {/* Name field */}
              <div>
                <label
                  htmlFor="task-name"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Name <span className="text-red-500">*</span>
                </label>
                <input
                  id="task-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-xs focus:outline-hidden focus:ring-primary focus:border-primary dark:bg-gray-700 dark:text-gray-300"
                  placeholder="Enter task name..."
                />
              </div>

              {/* Description field */}
              <div>
                <label
                  htmlFor="task-description"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Description
                </label>
                <textarea
                  id="task-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-xs focus:outline-hidden focus:ring-primary focus:border-primary dark:bg-gray-700 dark:text-gray-300"
                  rows={3}
                  placeholder="Describe what this task does..."
                />
              </div>

              {/* Script preview */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowScriptPreview(!showScriptPreview)}
                  className="flex items-center gap-1 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100"
                >
                  {showScriptPreview ? (
                    <ChevronUpIcon className="h-4 w-4" />
                  ) : (
                    <ChevronDownIcon className="h-4 w-4" />
                  )}
                  Script Preview
                </button>
                {showScriptPreview && (
                  <div className="mt-2 max-h-48 overflow-auto">
                    <pre className="text-xs font-mono bg-gray-900 text-gray-300 p-3 rounded-md whitespace-pre-wrap">
                      {initialScript || '(empty script)'}
                    </pre>
                  </div>
                )}
              </div>
            </div>

            {/* Actions - Fixed at bottom */}
            <div className="flex justify-end space-x-2 pt-4 border-t border-gray-200 dark:border-gray-700 mt-4 shrink-0">
              <button
                type="button"
                onClick={handleSafeClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600"
                disabled={isLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleSave()}
                className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isLoading || !name.trim()}
              >
                {isLoading ? 'Saving...' : 'Save'}
              </button>
            </div>
          </DialogPanel>
        </div>
      </Dialog>

      {/* Discard changes confirmation dialog */}
      <ConfirmDialog
        isOpen={showDiscardConfirm}
        onClose={() => setShowDiscardConfirm(false)}
        onConfirm={handleConfirmDiscard}
        title="Discard Unsaved Changes?"
        message="You have unsaved changes. Are you sure you want to exit? All your progress will be lost."
        confirmLabel="Discard Changes"
        cancelLabel="Keep Editing"
        variant="warning"
      />
    </>
  );
};
