import React from 'react';

import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';

interface ErrorMessageProps {
  message: string;
  onDismiss?: () => void;
  className?: string;
}

export const ErrorMessage: React.FC<ErrorMessageProps> = ({
  message,
  onDismiss,
  className = '',
}) => {
  return (
    <div
      className={`mb-4 p-3 bg-red-900/30 border border-red-700 rounded-md flex items-center ${className}`}
    >
      <ExclamationTriangleIcon className="h-5 w-5 text-red-500 mr-2" />
      <div className="flex-1">{message}</div>
      {onDismiss && (
        <button onClick={onDismiss} className="text-gray-300 hover:text-white text-sm">
          Dismiss
        </button>
      )}
    </div>
  );
};
