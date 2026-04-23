import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { startPolling, pollWithBackoff, createPoller } from '../polling';

describe('polling utilities', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  describe('startPolling', () => {
    it('should poll until shouldStop returns true', async () => {
      let attemptCount = 0;
      const mockPollFn = vi.fn(() => {
        attemptCount++;
        return Promise.resolve({
          status: attemptCount >= 3 ? 'completed' : 'running',
          attemptCount,
        });
      });

      const onComplete = vi.fn();

      startPolling({
        pollFn: mockPollFn,
        shouldStop: (result) => result.status === 'completed',
        onComplete,
      });

      // First poll happens immediately
      expect(mockPollFn).toHaveBeenCalledTimes(1);

      // Advance through the polling intervals
      await vi.advanceTimersByTimeAsync(500); // First delay
      expect(mockPollFn).toHaveBeenCalledTimes(2);

      await vi.advanceTimersByTimeAsync(500); // Second delay
      expect(mockPollFn).toHaveBeenCalledTimes(3);

      // Should have stopped after 3rd attempt
      expect(onComplete).toHaveBeenCalledWith({ status: 'completed', attemptCount: 3 }, 3);
    });

    it('should use custom delay intervals', async () => {
      let attemptCount = 0;
      const mockPollFn = vi.fn(() => {
        attemptCount++;
        return Promise.resolve({ count: attemptCount });
      });

      startPolling({
        pollFn: mockPollFn,
        shouldStop: (result) => result.count >= 4,
        delayIntervals: [100, 200, 300],
      });

      expect(mockPollFn).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(100);
      expect(mockPollFn).toHaveBeenCalledTimes(2);

      await vi.advanceTimersByTimeAsync(200);
      expect(mockPollFn).toHaveBeenCalledTimes(3);

      await vi.advanceTimersByTimeAsync(300); // Repeats last interval
      expect(mockPollFn).toHaveBeenCalledTimes(4);
    });

    it('should respect maxAttempts', async () => {
      const mockPollFn = vi.fn(() => Promise.resolve({ status: 'running' }));

      startPolling({
        pollFn: mockPollFn,
        shouldStop: () => false,
        maxAttempts: 3,
      });

      expect(mockPollFn).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(500);
      expect(mockPollFn).toHaveBeenCalledTimes(2);

      await vi.advanceTimersByTimeAsync(500);
      expect(mockPollFn).toHaveBeenCalledTimes(3);

      // Should not poll anymore after max attempts
      await vi.advanceTimersByTimeAsync(10_000);
      expect(mockPollFn).toHaveBeenCalledTimes(3);
    });

    it('should call onError when maxAttempts is exceeded', async () => {
      const mockPollFn = vi.fn(() => Promise.resolve({ status: 'running' }));
      const onError = vi.fn();
      const onComplete = vi.fn();

      startPolling({
        pollFn: mockPollFn,
        shouldStop: () => false,
        onError,
        onComplete,
        maxAttempts: 2,
      });

      expect(mockPollFn).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(500);
      expect(mockPollFn).toHaveBeenCalledTimes(2);

      // After maxAttempts, next tick should trigger onError
      await vi.advanceTimersByTimeAsync(500);

      expect(onError).toHaveBeenCalledTimes(1);
      expect(onError.mock.calls[0][0]).toBeInstanceOf(Error);
      expect(onError.mock.calls[0][0].message).toContain('Max polling attempts');
      expect(onComplete).not.toHaveBeenCalled();
    });

    it('should respect maxTotalTime', async () => {
      const mockPollFn = vi.fn(() => Promise.resolve({ status: 'running' }));

      startPolling({
        pollFn: mockPollFn,
        shouldStop: () => false,
        maxTotalTime: 1200, // Slightly more than first two intervals
      });

      expect(mockPollFn).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(500);
      expect(mockPollFn).toHaveBeenCalledTimes(2);

      await vi.advanceTimersByTimeAsync(500);
      expect(mockPollFn).toHaveBeenCalledTimes(3);

      // Should not poll anymore after max time
      await vi.advanceTimersByTimeAsync(10_000);
      expect(mockPollFn).toHaveBeenCalledTimes(3);
    });

    it('should call onError when maxTotalTime is exceeded', async () => {
      const mockPollFn = vi.fn(() => Promise.resolve({ status: 'running' }));
      const onError = vi.fn();
      const onComplete = vi.fn();

      startPolling({
        pollFn: mockPollFn,
        shouldStop: () => false,
        onError,
        onComplete,
        maxTotalTime: 600, // Slightly more than first interval
        delayIntervals: [500],
      });

      expect(mockPollFn).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(500);
      expect(mockPollFn).toHaveBeenCalledTimes(2);

      // Next tick should exceed maxTotalTime
      await vi.advanceTimersByTimeAsync(500);

      expect(onError).toHaveBeenCalledTimes(1);
      expect(onError.mock.calls[0][0]).toBeInstanceOf(Error);
      expect(onError.mock.calls[0][0].message).toContain('Max polling time');
      expect(onComplete).not.toHaveBeenCalled();
    });

    it('should handle errors with stopOnError true', async () => {
      const mockError = new Error('Poll failed');
      const mockPollFn = vi.fn(() => Promise.reject(mockError));

      const onError = vi.fn();

      startPolling({
        pollFn: mockPollFn,
        shouldStop: () => false,
        onError,
        stopOnError: true,
      });

      await vi.advanceTimersByTimeAsync(0);

      expect(onError).toHaveBeenCalledWith(mockError, 1);
      expect(mockPollFn).toHaveBeenCalledTimes(1);

      // Should not retry after error
      await vi.advanceTimersByTimeAsync(10_000);
      expect(mockPollFn).toHaveBeenCalledTimes(1);
    });

    it('should continue polling with stopOnError false', async () => {
      let attemptCount = 0;
      const mockPollFn = vi.fn(() => {
        attemptCount++;
        if (attemptCount === 1) {
          return Promise.reject(new Error('Temporary error'));
        }
        return Promise.resolve({ status: attemptCount >= 3 ? 'completed' : 'running' });
      });

      const onError = vi.fn();
      const onComplete = vi.fn();

      startPolling({
        pollFn: mockPollFn,
        shouldStop: (result) => result.status === 'completed',
        onError,
        onComplete,
        stopOnError: false,
      });

      await vi.advanceTimersByTimeAsync(0);
      expect(onError).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(500);
      expect(mockPollFn).toHaveBeenCalledTimes(2);

      await vi.advanceTimersByTimeAsync(500);
      expect(mockPollFn).toHaveBeenCalledTimes(3);
      expect(onComplete).toHaveBeenCalled();
    });

    it('should stop polling when stop() is called', async () => {
      const mockPollFn = vi.fn(() => Promise.resolve({ status: 'running' }));

      const controller = startPolling({
        pollFn: mockPollFn,
        shouldStop: () => false,
      });

      expect(mockPollFn).toHaveBeenCalledTimes(1);

      controller.stop();

      await vi.advanceTimersByTimeAsync(10_000);
      expect(mockPollFn).toHaveBeenCalledTimes(1);
    });
  });

  describe('pollWithBackoff', () => {
    it('should resolve with the final result', async () => {
      let attemptCount = 0;
      const mockPollFn = vi.fn(() => {
        attemptCount++;
        return Promise.resolve({
          status: attemptCount >= 2 ? 'completed' : 'running',
          data: 'result',
        });
      });

      const promise = pollWithBackoff(mockPollFn, (result) => result.status === 'completed');

      await vi.advanceTimersByTimeAsync(500);
      await vi.advanceTimersByTimeAsync(0);

      const result = await promise;
      expect(result).toEqual({ status: 'completed', data: 'result' });
    });

    it('should reject on error', async () => {
      const mockError = new Error('Poll failed');
      const mockPollFn = vi.fn(() => Promise.reject(mockError));

      const promise = pollWithBackoff(mockPollFn, () => false);

      // Catch the promise immediately to prevent unhandled rejection
      const resultPromise = promise.catch((error) => error);

      await vi.advanceTimersByTimeAsync(0);

      await expect(promise).rejects.toThrow('Poll failed');
      await resultPromise; // Ensure promise is settled
    });
  });

  describe('createPoller', () => {
    it('should create a reusable poller with default options', async () => {
      const poller = createPoller<{ status: string }>({
        delayIntervals: [100],
        maxAttempts: 2,
      });

      const mockPollFn = vi.fn(() => Promise.resolve({ status: 'running' }));

      poller(mockPollFn, () => false);

      expect(mockPollFn).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(100);
      expect(mockPollFn).toHaveBeenCalledTimes(2);

      // Should stop at max attempts
      await vi.advanceTimersByTimeAsync(1000);
      expect(mockPollFn).toHaveBeenCalledTimes(2);
    });

    it('should allow overriding default options', async () => {
      const poller = createPoller<{ status: string }>({
        delayIntervals: [100],
        maxAttempts: 5,
      });

      const mockPollFn = vi.fn(() => Promise.resolve({ status: 'running' }));

      poller(
        mockPollFn,
        () => false,
        { maxAttempts: 1 } // Override default
      );

      expect(mockPollFn).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(1000);
      expect(mockPollFn).toHaveBeenCalledTimes(1); // Stopped at overridden max
    });
  });
});
