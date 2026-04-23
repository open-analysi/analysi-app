import React from 'react';

interface ProgressBarProps {
  elapsedTime: number; // in seconds
  estimatedTime: number | null; // in seconds
  isRunning: boolean;
  isCompleted?: boolean; // Task completed but still showing for minimum time
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  elapsedTime,
  estimatedTime,
  isRunning,
  isCompleted = false,
}) => {
  if (!isRunning && !isCompleted) return null;

  const formatTime = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds}s`;
    }
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  };

  const percentage =
    estimatedTime && estimatedTime > 0 ? Math.min(100, (elapsedTime / estimatedTime) * 100) : 0;

  const isOverTime = estimatedTime && elapsedTime > estimatedTime;

  return (
    <div className="w-full space-y-2">
      <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400">
        <span>
          {isCompleted ? 'Completed in' : 'Elapsed'}: {formatTime(elapsedTime)}
        </span>
        {isCompleted ? (
          <span className="text-green-500 font-medium">✓ Task completed</span>
        ) : estimatedTime ? (
          <span className={isOverTime ? 'text-orange-500' : ''}>
            Estimated: {formatTime(estimatedTime)}
            {isOverTime && ' (exceeded)'}
          </span>
        ) : (
          <span>No time estimate available</span>
        )}
      </div>

      {isCompleted ? (
        <div className="relative w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div className="h-full w-full bg-green-500 transition-all duration-300" />
        </div>
      ) : estimatedTime ? (
        <div className="relative w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-100 rounded-full ${
              isOverTime
                ? 'bg-orange-500 animate-pulse'
                : percentage > 80
                  ? 'bg-yellow-500'
                  : 'bg-green-500'
            }`}
            style={{ width: `${percentage}%` }}
          />
          {!isOverTime && (
            <div className="absolute inset-0 bg-linear-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
          )}
        </div>
      ) : (
        <div className="relative w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div className="h-full w-full bg-linear-to-r from-blue-500 via-blue-400 to-blue-500 animate-pulse" />
        </div>
      )}

      {!isCompleted && estimatedTime && !isOverTime && elapsedTime < estimatedTime && (
        <div className="text-xs text-center text-gray-500 dark:text-gray-400">
          Remaining: ~{formatTime(Math.max(0, estimatedTime - elapsedTime))}
        </div>
      )}
    </div>
  );
};

export default ProgressBar;
