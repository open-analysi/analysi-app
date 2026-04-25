export const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';

  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${Number.parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

// Parse ISO 8601 duration format (e.g., "PT4.556137S") to seconds
// Also handles plain numeric strings (e.g., "45.5") as seconds
const parseISODuration = (input: string): number => {
  if (!input.startsWith('PT')) {
    // Try parsing as a plain number (seconds)
    const parsed = Number.parseFloat(input);
    return Number.isNaN(parsed) ? 0 : parsed;
  }

  // eslint-disable-next-line sonarjs/slow-regex -- simple numeric pattern, no backtracking risk
  const numPattern = /(\d+(?:\.\d+)?)\s*([HMS])/g;
  let totalSeconds = 0;
  let match: RegExpExecArray | null;

  while ((match = numPattern.exec(input)) !== null) {
    const value = Number.parseFloat(match[1]);
    const unit = match[2];
    if (unit === 'H') totalSeconds += value * 3600;
    else if (unit === 'M') totalSeconds += value * 60;
    else if (unit === 'S') totalSeconds += value;
  }

  return totalSeconds;
};

/**
 * Returns a Tailwind color class based on duration.
 *
 * For tasks (default):
 * - green: < 5s  (fast)
 * - yellow: 5–30s  (moderate)
 * - red: > 30s  (slow)
 *
 * For workflows:
 * - green: < 60s (1 minute)
 * - yellow: 60s–600s (1-10 minutes)
 * - red: >= 600s (10+ minutes)
 */
export const getDurationColorClass = (
  input: number | string,
  type: 'task' | 'workflow' = 'task'
): string => {
  const seconds = typeof input === 'string' ? parseISODuration(input) : input;

  if (type === 'workflow') {
    // Workflows have longer expected durations
    if (seconds < 60) return 'text-green-500 dark:text-green-400';
    if (seconds < 600) return 'text-yellow-500 dark:text-yellow-400';
    return 'text-red-500 dark:text-red-400';
  }

  // Default task thresholds
  if (seconds < 5) return 'text-green-500 dark:text-green-400';
  if (seconds < 30) return 'text-yellow-500 dark:text-yellow-400';
  return 'text-red-500 dark:text-red-400';
};

export const formatDuration = (input: number | string): string => {
  let seconds: number;

  // Handle both number (seconds) and string (ISO 8601 format)
  seconds = typeof input === 'string' ? parseISODuration(input) : input;

  if (seconds < 1) {
    return `${Math.round(seconds * 1000)}ms`;
  }

  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds.toFixed(1)}s`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  return `${hours}h ${remainingMinutes}m`;
};
