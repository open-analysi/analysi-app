import React from 'react';

import { Description, Dialog, DialogPanel, DialogTitle } from '@headlessui/react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';

interface RunUnsavedChangesDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSaveAndRun: () => void;
  onSaveAsAndRun: () => void;
  taskName?: string;
}

export const RunUnsavedChangesDialog: React.FC<RunUnsavedChangesDialogProps> = ({
  isOpen,
  onClose,
  onSaveAndRun,
  onSaveAsAndRun,
  taskName,
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
                Run with Unsaved Changes?
              </DialogTitle>
              <Description className="mt-2 text-sm text-gray-300">
                {taskName ? (
                  <>
                    You have unsaved changes to <strong className="text-white">{taskName}</strong>.
                    How would you like to proceed?
                  </>
                ) : (
                  <>You have unsaved changes. How would you like to proceed?</>
                )}
              </Description>
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-2">
            {/* Save and Run button */}
            <button
              onClick={onSaveAndRun}
              className="w-full px-4 py-2 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary/90 transition-colors"
            >
              Save and Run
            </button>

            {/* Save As and Run button */}
            <button
              onClick={onSaveAsAndRun}
              className="w-full px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
            >
              Save As New Task and Run...
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
