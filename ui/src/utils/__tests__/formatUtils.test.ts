import { describe, it, expect } from 'vitest';

import { formatBytes, formatDuration, getDurationColorClass } from '../formatUtils';

describe('formatBytes', () => {
  it('returns "0 B" for zero bytes', () => {
    expect(formatBytes(0)).toBe('0 B');
  });

  it('formats bytes correctly', () => {
    expect(formatBytes(500)).toBe('500 B');
  });

  it('formats kilobytes correctly', () => {
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatBytes(1536)).toBe('1.5 KB');
  });

  it('formats megabytes correctly', () => {
    expect(formatBytes(1048576)).toBe('1 MB');
    expect(formatBytes(2621440)).toBe('2.5 MB');
  });

  it('formats gigabytes correctly', () => {
    expect(formatBytes(1073741824)).toBe('1 GB');
  });

  it('formats terabytes correctly', () => {
    expect(formatBytes(1099511627776)).toBe('1 TB');
  });
});

describe('formatDuration', () => {
  describe('numeric input (seconds)', () => {
    it('formats sub-second durations as milliseconds', () => {
      expect(formatDuration(0.5)).toBe('500ms');
      expect(formatDuration(0.123)).toBe('123ms');
      expect(formatDuration(0.001)).toBe('1ms');
    });

    it('formats seconds with one decimal', () => {
      expect(formatDuration(1)).toBe('1.0s');
      expect(formatDuration(4.556)).toBe('4.6s');
      expect(formatDuration(59.9)).toBe('59.9s');
    });

    it('formats minutes and seconds', () => {
      expect(formatDuration(60)).toBe('1m 0.0s');
      expect(formatDuration(90)).toBe('1m 30.0s');
      expect(formatDuration(3599)).toBe('59m 59.0s');
    });

    it('formats hours and minutes', () => {
      expect(formatDuration(3600)).toBe('1h 0m');
      expect(formatDuration(3660)).toBe('1h 1m');
      expect(formatDuration(7200)).toBe('2h 0m');
    });
  });

  describe('ISO 8601 duration string input', () => {
    it('parses PT seconds format', () => {
      expect(formatDuration('PT4.556137S')).toBe('4.6s');
      expect(formatDuration('PT0.5S')).toBe('500ms');
      expect(formatDuration('PT30S')).toBe('30.0s');
    });

    it('parses PT minutes and seconds', () => {
      expect(formatDuration('PT1M30S')).toBe('1m 30.0s');
      expect(formatDuration('PT5M')).toBe('5m 0.0s');
    });

    it('parses PT hours, minutes, and seconds', () => {
      expect(formatDuration('PT1H30M15S')).toBe('1h 30m');
      expect(formatDuration('PT2H')).toBe('2h 0m');
    });

    it('parses plain numeric strings as seconds', () => {
      expect(formatDuration('45.5')).toBe('45.5s');
      expect(formatDuration('0.5')).toBe('500ms');
    });

    it('returns 0ms for unparseable input', () => {
      expect(formatDuration('invalid')).toBe('0ms');
    });
  });
});

describe('getDurationColorClass', () => {
  const GREEN = 'text-green-500 dark:text-green-400';
  const YELLOW = 'text-yellow-500 dark:text-yellow-400';
  const RED = 'text-red-500 dark:text-red-400';

  describe('task type (default)', () => {
    it('returns green for fast tasks (< 5s)', () => {
      expect(getDurationColorClass(0)).toBe(GREEN);
      expect(getDurationColorClass(4.9)).toBe(GREEN);
    });

    it('returns yellow for moderate tasks (5-30s)', () => {
      expect(getDurationColorClass(5)).toBe(YELLOW);
      expect(getDurationColorClass(15)).toBe(YELLOW);
      expect(getDurationColorClass(29.9)).toBe(YELLOW);
    });

    it('returns red for slow tasks (>= 30s)', () => {
      expect(getDurationColorClass(30)).toBe(RED);
      expect(getDurationColorClass(120)).toBe(RED);
    });

    it('parses ISO duration strings', () => {
      expect(getDurationColorClass('PT2S')).toBe(GREEN);
      expect(getDurationColorClass('PT10S')).toBe(YELLOW);
      expect(getDurationColorClass('PT1M')).toBe(RED);
    });
  });

  describe('workflow type', () => {
    it('returns green for fast workflows (< 60s)', () => {
      expect(getDurationColorClass(0, 'workflow')).toBe(GREEN);
      expect(getDurationColorClass(59, 'workflow')).toBe(GREEN);
    });

    it('returns yellow for moderate workflows (60-600s)', () => {
      expect(getDurationColorClass(60, 'workflow')).toBe(YELLOW);
      expect(getDurationColorClass(300, 'workflow')).toBe(YELLOW);
      expect(getDurationColorClass(599, 'workflow')).toBe(YELLOW);
    });

    it('returns red for slow workflows (>= 600s)', () => {
      expect(getDurationColorClass(600, 'workflow')).toBe(RED);
      expect(getDurationColorClass(3600, 'workflow')).toBe(RED);
    });

    it('parses ISO duration strings for workflows', () => {
      expect(getDurationColorClass('PT30S', 'workflow')).toBe(GREEN);
      expect(getDurationColorClass('PT5M', 'workflow')).toBe(YELLOW);
      expect(getDurationColorClass('PT15M', 'workflow')).toBe(RED);
    });
  });
});
