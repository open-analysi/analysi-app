import { describe, it, expect } from 'vitest';

import { getSeverityOrder, severityOrder } from '../../utils/severityUtils';
import { getMinutes } from '../../utils/timeUtils';

describe('getMinutes function', () => {
  it('extracts minutes from minute-only format', () => {
    expect(getMinutes('45m')).toBe(45);
    expect(getMinutes('0m')).toBe(0);
    expect(getMinutes('1m')).toBe(1);
    expect(getMinutes('999m')).toBe(999);
  });

  it('extracts minutes from hour-only format', () => {
    expect(getMinutes('1h')).toBe(60);
    expect(getMinutes('2h')).toBe(120);
    expect(getMinutes('24h')).toBe(1440);
  });

  it('extracts minutes from combined format', () => {
    expect(getMinutes('1h 30m')).toBe(90);
    expect(getMinutes('2h 15m')).toBe(135);
    expect(getMinutes('5h 0m')).toBe(300);
  });

  it('handles spaces and formatting variations', () => {
    expect(getMinutes('1h30m')).toBe(90);
    expect(getMinutes('1h  30m')).toBe(90);
    expect(getMinutes(' 1h 30m ')).toBe(90);
  });

  it('returns 0 for invalid formats', () => {
    expect(getMinutes('')).toBe(0);
    expect(getMinutes('invalid')).toBe(0);
    expect(getMinutes('h m')).toBe(0);
  });

  it('ignores non-numeric characters', () => {
    expect(getMinutes('abc2habc 30mabc')).toBe(150);
  });
});

describe('Severity sorting', () => {
  it('should have correct severity order definition', () => {
    expect(severityOrder.Critical).toBe(0);
    expect(severityOrder.High).toBe(1);
    expect(severityOrder.Medium).toBe(2);
    expect(severityOrder.Low).toBe(3);
  });

  it('should get correct order values', () => {
    // Test the ordering
    expect(getSeverityOrder('Critical')).toBeLessThan(getSeverityOrder('High'));
    expect(getSeverityOrder('High')).toBeLessThan(getSeverityOrder('Medium'));
    expect(getSeverityOrder('Medium')).toBeLessThan(getSeverityOrder('Low'));

    // Test unknown severity
    expect(getSeverityOrder('Unknown')).toBe(999);
  });

  it('should sort severity array correctly', () => {
    // Test sorting an array
    const severities = ['Medium', 'Critical', 'Low', 'High', 'Unknown'];
    const sorted = [...severities].sort((a, b) => getSeverityOrder(a) - getSeverityOrder(b));

    expect(sorted).toEqual(['Critical', 'High', 'Medium', 'Low', 'Unknown']);
  });
});
