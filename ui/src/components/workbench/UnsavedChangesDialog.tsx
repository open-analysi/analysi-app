import React from 'react';

import { Description, Dialog, DialogPanel, DialogTitle } from '@headlessui/react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';

interface UnsavedChangesDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: () => void;
  onSaveAs: () => void;
  onDiscard: () => void;
  taskName?: string;
  canSave: boolean; // Whether Save button should be enabled (false for ad-hoc mode)
}

export const UnsavedChangesDialog: React.FC<UnsavedChangesDialogProps> = ({
  isOpen,
  onClose,
  onSave,
  onSaveAs,
  onDiscard,
  taskName,
  canSave,
}) => {
  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/50" aria-hidden="true" />

      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel className="mx-auto max-w-md rounded-xl bg-dark-800 p-6 shadow-xl border border-gray-700">
          <div className="flex items-start gap-4">
            <div className="shrink-0 p-2 bg-yellow-500/10 rounded-full">
              <ExclamationTriangleIcon className="h-6 w-6 text-yellow-500" />
            </div>
            <div className="flex-1">
              <DialogTitle className="text-lg font-semibold text-white">
                Unsaved Changes
              </DialogTitle>
              <Description className="mt-2 text-sm text-gray-300">
                {taskName ? (
                  <>
                    You have unsaved changes to <strong className="text-white">{taskName}</strong>.
                    What would you like to do?
                  </>
                ) : (
                  <>You have unsaved changes. What would you like to do?</>
                )}
              </Description>
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-2">
            {/* Save button - only show if we can save (not in ad-hoc mode) */}
            {canSave && (
              <button
                onClick={onSave}
                className="w-full px-4 py-2 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary/90 transition-colors"
              >
                Save Changes
              </button>
            )}

            {/* Save As button */}
            <button
              onClick={onSaveAs}
              className="w-full px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
            >
              Save As New Task...
            </button>

            {/* Discard button */}
            <button
              onClick={onDiscard}
              className="w-full px-4 py-2 text-sm font-medium text-red-400 bg-transparent border border-red-400/50 rounded-md hover:bg-red-400/10 transition-colors"
            >
              Discard Changes
            </button>

            {/* Cancel button */}
            <button
              onClick={onClose}
              className="w-full px-4 py-2 text-sm font-medium text-gray-400 bg-transparent rounded-md hover:text-white hover:bg-gray-700 transition-colors"
            >
              Cancel
            </button>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  );
};
