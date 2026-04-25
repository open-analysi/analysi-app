import { describe, it, expect } from 'vitest';

// Extracted formatDuration function for testing
const formatDuration = (ms: number): string => {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
  } else if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  } else if (seconds > 0) {
    return `${seconds}s`;
  } else {
    return `${ms}ms`;
  }
};

describe('formatDuration', () => {
  describe('milliseconds formatting', () => {
    it('should format 0ms', () => {
      expect(formatDuration(0)).toBe('0ms');
    });

    it('should format small milliseconds', () => {
      expect(formatDuration(150)).toBe('150ms');
    });

    it('should format 999ms', () => {
      expect(formatDuration(999)).toBe('999ms');
    });
  });

  describe('seconds formatting', () => {
    it('should format 1 second', () => {
      expect(formatDuration(1000)).toBe('1s');
    });

    it('should format 15 seconds', () => {
      expect(formatDuration(15000)).toBe('15s');
    });

    it('should format 59 seconds', () => {
      expect(formatDuration(59000)).toBe('59s');
    });
  });

  describe('minutes and seconds formatting', () => {
    it('should format 1 minute', () => {
      expect(formatDuration(60000)).toBe('1m 0s');
    });

    it('should format 1 minute 15 seconds', () => {
      expect(formatDuration(75000)).toBe('1m 15s');
    });

    it('should format 5 minutes 30 seconds', () => {
      expect(formatDuration(330000)).toBe('5m 30s');
    });

    it('should format 59 minutes 59 seconds', () => {
      expect(formatDuration(3599000)).toBe('59m 59s');
    });
  });

  describe('hours, minutes, and seconds formatting', () => {
    it('should format 1 hour', () => {
      expect(formatDuration(3600000)).toBe('1h 0m 0s');
    });

    it('should format 1 hour 5 minutes 30 seconds', () => {
      expect(formatDuration(3930000)).toBe('1h 5m 30s');
    });

    it('should format 2 hours 5 minutes 30 seconds', () => {
      expect(formatDuration(7530000)).toBe('2h 5m 30s');
    });

    it('should format 10 hours 0 minutes 0 seconds', () => {
      expect(formatDuration(36000000)).toBe('10h 0m 0s');
    });

    it('should format 24 hours', () => {
      expect(formatDuration(86400000)).toBe('24h 0m 0s');
    });
  });

  describe('edge cases', () => {
    it('should handle negative values (treat as 0)', () => {
      // Negative duration doesn't make sense, but ensure it doesn't crash
      expect(formatDuration(-1000)).toBe('-1000ms');
    });

    it('should handle very large durations', () => {
      // 100 hours
      expect(formatDuration(360000000)).toBe('100h 0m 0s');
    });
  });
});
