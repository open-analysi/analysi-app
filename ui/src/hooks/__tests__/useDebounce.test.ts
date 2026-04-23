import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { useDebounce } from '../useDebounce';

describe('useDebounce', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns the initial value immediately', () => {
    const { result } = renderHook(() => useDebounce('hello', 300));
    expect(result.current).toBe('hello');
  });

  it('does not update the debounced value before the delay', () => {
    const { result, rerender } = renderHook(({ value, delay }) => useDebounce(value, delay), {
      initialProps: { value: 'initial', delay: 300 },
    });

    rerender({ value: 'updated', delay: 300 });

    // Before delay expires, value should still be initial
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current).toBe('initial');
  });

  it('updates the debounced value after the delay', () => {
    const { result, rerender } = renderHook(({ value, delay }) => useDebounce(value, delay), {
      initialProps: { value: 'initial', delay: 300 },
    });

    rerender({ value: 'updated', delay: 300 });

    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(result.current).toBe('updated');
  });

  it('resets the timer when value changes rapidly', () => {
    const { result, rerender } = renderHook(({ value, delay }) => useDebounce(value, delay), {
      initialProps: { value: 'a', delay: 300 },
    });

    // Rapidly change value
    rerender({ value: 'b', delay: 300 });
    act(() => {
      vi.advanceTimersByTime(100);
    });

    rerender({ value: 'c', delay: 300 });
    act(() => {
      vi.advanceTimersByTime(100);
    });

    rerender({ value: 'd', delay: 300 });

    // Only 200ms since last change — still initial
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current).toBe('a');

    // After full delay from last change, should be 'd'
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current).toBe('d');
  });

  it('works with numeric values', () => {
    const { result, rerender } = renderHook(({ value, delay }) => useDebounce(value, delay), {
      initialProps: { value: 0, delay: 500 },
    });

    rerender({ value: 42, delay: 500 });

    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(result.current).toBe(42);
  });

  it('works with object values', () => {
    const initial = { search: '' };
    const updated = { search: 'test' };

    const { result, rerender } = renderHook(({ value, delay }) => useDebounce(value, delay), {
      initialProps: { value: initial, delay: 200 },
    });

    rerender({ value: updated, delay: 200 });

    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current).toEqual({ search: 'test' });
  });
});
