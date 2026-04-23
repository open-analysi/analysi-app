export interface PollingOptions<T> {
  /**
   * Function to check if polling should continue
   * Return true to stop polling, false to continue
   */
  shouldStop: (result: T) => boolean;

  /**
   * Function to execute on each poll
   */
  pollFn: () => Promise<T>;

  /**
   * Optional callback for each poll result
   */
  onPoll?: (result: T, attemptNumber: number) => void;

  /**
   * Optional callback when polling stops
   */
  onComplete?: (result: T, attemptNumber: number) => void;

  /**
   * Optional callback for errors
   */
  onError?: (error: Error, attemptNumber: number) => void;

  /**
   * Maximum number of attempts (default: no limit)
   */
  maxAttempts?: number;

  /**
   * Maximum total time in milliseconds (default: no limit)
   */
  maxTotalTime?: number;

  /**
   * Custom delay intervals in milliseconds
   * Default: [500, 500, 1000, 2000, 3000, 5000] then repeats 5000
   */
  delayIntervals?: number[];

  /**
   * Whether to stop on error (default: true)
   */
  stopOnError?: boolean;
}

export interface PollingController {
  /**
   * Stop the polling
   */
  stop: () => void;

  /**
   * Promise that resolves when polling completes
   */
  promise: Promise<void>;
}

/**
 * Default delay intervals: 500ms, 500ms, 1s, 2s, 3s, then 5s repeatedly
 */
const DEFAULT_DELAY_INTERVALS = [500, 500, 1000, 2000, 3000, 5000];

/**
 * Custom polling utility with configurable delay intervals
 *
 * @example
 * ```ts
 * const controller = startPolling({
 *   pollFn: async () => await checkTaskStatus(taskId),
 *   shouldStop: (result) => result.status !== 'running',
 *   onComplete: (result) => console.log('Task completed:', result),
 *   maxAttempts: 20,
 *   maxTotalTime: 60000 // 1 minute
 * });
 *
 * // To stop polling manually:
 * controller.stop();
 * ```
 */
export function startPolling<T>(options: PollingOptions<T>): PollingController {
  const {
    shouldStop,
    pollFn,
    onPoll,
    onComplete,
    onError,
    maxAttempts = Number.POSITIVE_INFINITY,
    maxTotalTime = Number.POSITIVE_INFINITY,
    delayIntervals = DEFAULT_DELAY_INTERVALS,
    stopOnError = true,
  } = options;

  let isRunning = true;
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const startTime = Date.now();

  const stop = () => {
    isRunning = false;
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = undefined;
    }
  };

  const getDelay = (attemptNumber: number): number => {
    // Use custom intervals, then repeat the last one
    const index = Math.min(attemptNumber - 1, delayIntervals.length - 1);
    return delayIntervals[index];
  };

  const poll = async (attemptNumber: number): Promise<void> => {
    if (!isRunning) {
      return;
    }

    // Check max attempts
    if (attemptNumber > maxAttempts) {
      stop();
      onError?.(new Error(`Max polling attempts (${maxAttempts}) reached`), attemptNumber);
      return;
    }

    // Check max total time
    const elapsedTime = Date.now() - startTime;
    if (elapsedTime > maxTotalTime) {
      stop();
      onError?.(new Error(`Max polling time (${maxTotalTime}ms) exceeded`), attemptNumber);
      return;
    }

    try {
      const result = await pollFn();

      if (!isRunning) {
        return;
      }

      // Call onPoll callback if provided
      onPoll?.(result, attemptNumber);

      // Check if we should stop
      if (shouldStop(result)) {
        stop();
        onComplete?.(result, attemptNumber);
        return;
      }

      // Schedule next poll
      const delay = getDelay(attemptNumber);
      timeoutId = setTimeout(() => {
        void poll(attemptNumber + 1);
      }, delay);
    } catch (error) {
      if (!isRunning) {
        return;
      }

      const err = error instanceof Error ? error : new Error(String(error));
      onError?.(err, attemptNumber);

      if (stopOnError) {
        stop();
        return;
      }

      // Continue polling even after error
      const delay = getDelay(attemptNumber);
      timeoutId = setTimeout(() => {
        void poll(attemptNumber + 1);
      }, delay);
    }
  };

  // Start polling
  const promise = poll(1);

  return {
    stop,
    promise,
  };
}

/**
 * Simple exponential backoff polling for common use cases
 *
 * @example
 * ```ts
 * const result = await pollWithBackoff(
 *   async () => await checkTaskStatus(taskId),
 *   (result) => result.status !== 'running',
 *   { maxAttempts: 20 }
 * );
 * ```
 */
export async function pollWithBackoff<T>(
  pollFn: () => Promise<T>,
  shouldStop: (result: T) => boolean,
  options: Partial<Omit<PollingOptions<T>, 'pollFn' | 'shouldStop'>> = {}
): Promise<T> {
  return new Promise((resolve, reject) => {
    startPolling({
      pollFn,
      shouldStop,
      onComplete: (result) => {
        resolve(result);
      },
      onError: (error) => {
        reject(error);
      },
      ...options,
    });
  });
}

/**
 * Create a reusable polling configuration
 *
 * @example
 * ```ts
 * const taskPoller = createPoller<TaskStatus>({
 *   delayIntervals: [100, 200, 500, 1000, 2000],
 *   maxAttempts: 30
 * });
 *
 * const controller = taskPoller(
 *   async () => await getTaskStatus(taskId),
 *   (status) => status.state !== 'running'
 * );
 * ```
 */
export function createPoller<T>(
  defaultOptions: Partial<Omit<PollingOptions<T>, 'pollFn' | 'shouldStop'>> = {}
) {
  return (
    pollFn: () => Promise<T>,
    shouldStop: (result: T) => boolean,
    overrideOptions: Partial<Omit<PollingOptions<T>, 'pollFn' | 'shouldStop'>> = {}
  ): PollingController => {
    return startPolling({
      pollFn,
      shouldStop,
      ...defaultOptions,
      ...overrideOptions,
    });
  };
}
