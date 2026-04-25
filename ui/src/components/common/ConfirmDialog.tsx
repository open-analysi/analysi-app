/**
 * ConfirmDialog - Reusable confirmation modal
 *
 * Replaces window.confirm() with a styled modal dialog.
 * Can be used with the useConfirmDialog hook for async/await pattern.
 */
import React from 'react';

import { Description, Dialog, DialogPanel, DialogTitle } from '@headlessui/react';
import {
  ExclamationTriangleIcon,
  InformationCircleIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/react/24/outline';

export type ConfirmDialogVariant = 'info' | 'warning' | 'question';

export interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: ConfirmDialogVariant;
}

const variantConfig: Record<
  ConfirmDialogVariant,
  {
    icon: React.ElementType;
    iconBg: string;
    iconColor: string;
    buttonColor: string;
  }
> = {
  info: {
    icon: InformationCircleIcon,
    iconBg: 'bg-blue-500/20',
    iconColor: 'text-blue-400',
    buttonColor: 'bg-blue-600 hover:bg-blue-700',
  },
  warning: {
    icon: ExclamationTriangleIcon,
    iconBg: 'bg-yellow-500/20',
    iconColor: 'text-yellow-400',
    buttonColor: 'bg-yellow-600 hover:bg-yellow-700',
  },
  question: {
    icon: QuestionMarkCircleIcon,
    iconBg: 'bg-primary/20',
    iconColor: 'text-primary',
    buttonColor: 'bg-primary hover:bg-primary/90',
  },
};

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'question',
}) => {
  const config = variantConfig[variant];
  const IconComponent = config.icon;

  // Note: We only call onConfirm, not onClose. The caller is responsible for
  // closing the dialog. This prevents issues where onClose has different
  // semantics than onConfirm (e.g., "cancel" vs "confirm" actions).
  const handleConfirm = () => {
    onConfirm();
  };

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/60" aria-hidden="true" />

      {/* Full-screen container for centering */}
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel className="mx-auto max-w-md rounded-lg bg-dark-800 border border-gray-700 shadow-xl">
          <div className="p-6">
            {/* Icon and Title */}
            <div className="flex items-start space-x-4">
              <div className={`p-2 rounded-full ${config.iconBg}`}>
                <IconComponent className={`h-6 w-6 ${config.iconColor}`} />
              </div>
              <div className="flex-1">
                <DialogTitle className="text-lg font-semibold text-white">{title}</DialogTitle>
                <Description className="mt-2 text-sm text-gray-300">{message}</Description>
              </div>
            </div>

            {/* Actions */}
            <div className="mt-6 flex justify-end space-x-3">
              {cancelLabel && (
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-sm font-medium text-gray-300 bg-dark-700 border border-gray-600 rounded-md hover:bg-dark-600 focus:outline-hidden focus:ring-2 focus:ring-gray-500"
                >
                  {cancelLabel}
                </button>
              )}
              <button
                type="button"
                onClick={handleConfirm}
                className={`px-4 py-2 text-sm font-medium text-white rounded-md focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-offset-dark-800 ${config.buttonColor}`}
              >
                {confirmLabel}
              </button>
            </div>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  );
};

/**
 * Hook for using ConfirmDialog with async/await pattern
 *
 * Usage:
 * ```tsx
 * const { confirm, ConfirmDialogComponent } = useConfirmDialog();
 *
 * const handleAction = async () => {
 *   const confirmed = await confirm({
 *     title: 'Restore Draft?',
 *     message: 'Found unsaved changes. Restore them?',
 *   });
 *   if (confirmed) {
 *     // do something
 *   }
 * };
 *
 * return (
 *   <>
 *     <button onClick={handleAction}>Click</button>
 *     {ConfirmDialogComponent}
 *   </>
 * );
 * ```
 */
export interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: ConfirmDialogVariant;
}

interface ConfirmState extends ConfirmOptions {
  isOpen: boolean;
  resolve: ((value: boolean) => void) | null;
}

export function useConfirmDialog() {
  const [state, setState] = React.useState<ConfirmState>({
    isOpen: false,
    title: '',
    message: '',
    resolve: null,
  });

  const confirm = React.useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({
        ...options,
        isOpen: true,
        resolve,
      });
    });
  }, []);

  const handleClose = React.useCallback(() => {
    state.resolve?.(false);
    setState((prev) => ({ ...prev, isOpen: false, resolve: null }));
  }, [state]);

  const handleConfirm = React.useCallback(() => {
    state.resolve?.(true);
    setState((prev) => ({ ...prev, isOpen: false, resolve: null }));
  }, [state]);

  const ConfirmDialogComponent = (
    <ConfirmDialog
      isOpen={state.isOpen}
      onClose={handleClose}
      onConfirm={handleConfirm}
      title={state.title}
      message={state.message}
      confirmLabel={state.confirmLabel}
      cancelLabel={state.cancelLabel}
      variant={state.variant}
    />
  );

  return { confirm, ConfirmDialogComponent };
}

export default ConfirmDialog;
