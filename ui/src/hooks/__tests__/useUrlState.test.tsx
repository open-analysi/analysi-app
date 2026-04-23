import React from 'react';

import { renderHook, act } from '@testing-library/react';
import { MemoryRouter, useSearchParams } from 'react-router';
import { describe, it, expect } from 'vitest';

import { useUrlState, useUrlStateObject } from '../useUrlState';

// Helper wrapper for router context
function createWrapper(initialUrl = '') {
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <MemoryRouter initialEntries={[initialUrl]}>{children}</MemoryRouter>
  );
  Wrapper.displayName = 'TestRouterWrapper';
  return Wrapper;
}

describe('useUrlState', () => {
  describe('basic functionality', () => {
    it('should return default value when no URL parameter exists', () => {
      const { result } = renderHook(() => useUrlState('tab', 'details'), {
        wrapper: createWrapper('/page'),
      });

      expect(result.current[0]).toBe('details');
    });

    it('should read initial value from URL', () => {
      const { result } = renderHook(() => useUrlState('tab', 'details'), {
        wrapper: createWrapper('/page?tab=workflow'),
      });

      expect(result.current[0]).toBe('workflow');
    });

    it('should update URL when value changes', () => {
      const { result } = renderHook(
        () => {
          const [value, setValue] = useUrlState<string>('tab', 'details');
          const [searchParams] = useSearchParams();
          return { value, setValue, searchParams };
        },
        { wrapper: createWrapper('/page') }
      );

      act(() => {
        result.current.setValue('workflow');
      });

      expect(result.current.value).toBe('workflow');
      expect(result.current.searchParams.get('tab')).toBe('workflow');
    });

    it('should remove parameter when setting to default value', () => {
      const { result } = renderHook(
        () => {
          const [value, setValue] = useUrlState('tab', 'details');
          const [searchParams] = useSearchParams();
          return { value, setValue, searchParams };
        },
        { wrapper: createWrapper('/page?tab=workflow') }
      );

      act(() => {
        result.current.setValue('details'); // Set back to default
      });

      expect(result.current.value).toBe('details');
      expect(result.current.searchParams.has('tab')).toBe(false);
    });

    it('should support function updates like useState', () => {
      const { result } = renderHook(() => useUrlState<string>('count', '1'), {
        wrapper: createWrapper('/page'),
      });

      act(() => {
        result.current[1]((prev) => String(Number(prev) + 1));
      });

      expect(result.current[0]).toBe('2');
    });
  });

  describe('type coercion', () => {
    it('should handle number type coercion', () => {
      const { result } = renderHook(() => useUrlState('page', 1, { type: 'number' }), {
        wrapper: createWrapper('/page?page=5'),
      });

      expect(result.current[0]).toBe(5);
      expect(typeof result.current[0]).toBe('number');
    });

    it('should handle boolean type coercion', () => {
      const { result: resultTrue } = renderHook(
        () => useUrlState('show', false, { type: 'boolean' }),
        { wrapper: createWrapper('/page?show=true') }
      );

      expect(resultTrue.current[0]).toBe(true);
      expect(typeof resultTrue.current[0]).toBe('boolean');

      const { result: resultFalse } = renderHook(
        () => useUrlState('show', true, { type: 'boolean' }),
        { wrapper: createWrapper('/page?show=false') }
      );

      expect(resultFalse.current[0]).toBe(false);
    });

    it('should infer type from default value', () => {
      const { result: numberResult } = renderHook(() => useUrlState('count', 10), {
        wrapper: createWrapper('/page?count=25'),
      });
      expect(numberResult.current[0]).toBe(25);
      expect(typeof numberResult.current[0]).toBe('number');

      const { result: boolResult } = renderHook(() => useUrlState('enabled', true), {
        wrapper: createWrapper('/page?enabled=false'),
      });
      expect(boolResult.current[0]).toBe(false);
      expect(typeof boolResult.current[0]).toBe('boolean');
    });

    it('should return default for invalid number', () => {
      const { result } = renderHook(() => useUrlState('page', 1, { type: 'number' }), {
        wrapper: createWrapper('/page?page=invalid'),
      });

      expect(result.current[0]).toBe(1);
    });
  });

  describe('history behavior', () => {
    it('should update value with replace by default', () => {
      const { result } = renderHook(() => useUrlState<string>('tab', 'details'), {
        wrapper: createWrapper('/page'),
      });

      // Initial state
      expect(result.current[0]).toBe('details');

      act(() => {
        result.current[1]('workflow');
      });

      // Value should be updated
      expect(result.current[0]).toBe('workflow');
    });

    it('should update value with replace option', () => {
      const { result } = renderHook(
        () => useUrlState<string>('tab', 'details', { replace: false }),
        { wrapper: createWrapper('/page') }
      );

      // Initial state
      expect(result.current[0]).toBe('details');

      act(() => {
        result.current[1]('workflow');
      });

      // Value should be updated
      expect(result.current[0]).toBe('workflow');
    });
  });
});

describe('useUrlStateObject', () => {
  it('should handle multiple values at once', () => {
    const defaults = {
      status: 'all',
      priority: 'any',
      search: '',
    };

    const { result } = renderHook(
      () => {
        const [values, setValues] = useUrlStateObject(defaults);
        const [searchParams] = useSearchParams();
        return { values, setValues, searchParams };
      },
      { wrapper: createWrapper('/page?status=active&priority=high') }
    );

    expect(result.current.values).toEqual({
      status: 'active',
      priority: 'high',
      search: '',
    });
  });

  it('should update multiple values at once', () => {
    const defaults = {
      status: 'all',
      priority: 'any',
      search: '',
    };

    const { result } = renderHook(
      () => {
        const [values, setValues] = useUrlStateObject(defaults);
        const [searchParams] = useSearchParams();
        return { values, setValues, searchParams };
      },
      { wrapper: createWrapper('/page') }
    );

    act(() => {
      result.current.setValues({
        status: 'active',
        search: 'test',
      });
    });

    expect(result.current.values.status).toBe('active');
    expect(result.current.values.search).toBe('test');
    expect(result.current.searchParams.get('status')).toBe('active');
    expect(result.current.searchParams.get('search')).toBe('test');
  });

  it('should clear all values to defaults', () => {
    const defaults = {
      status: 'all',
      priority: 'any',
    };

    const { result } = renderHook(
      () => {
        const [values, setValues, clearValues] = useUrlStateObject(defaults);
        const [searchParams] = useSearchParams();
        return { values, setValues, clearValues, searchParams };
      },
      { wrapper: createWrapper('/page?status=active&priority=high') }
    );

    act(() => {
      result.current.clearValues();
    });

    expect(result.current.values).toEqual(defaults);
    expect(result.current.searchParams.has('status')).toBe(false);
    expect(result.current.searchParams.has('priority')).toBe(false);
  });

  it('should handle mixed types in object', () => {
    const defaults = {
      page: 1,
      search: '',
      showDetails: false,
    };

    const { result } = renderHook(() => useUrlStateObject(defaults), {
      wrapper: createWrapper('/page?page=3&search=test&showDetails=true'),
    });

    expect(result.current[0]).toEqual({
      page: 3,
      search: 'test',
      showDetails: true,
    });
    expect(typeof result.current[0].page).toBe('number');
    expect(typeof result.current[0].showDetails).toBe('boolean');
  });

  it('should clean defaults from URL in object mode', () => {
    const defaults = {
      status: 'all',
      priority: 'any',
    };

    const { result } = renderHook(
      () => {
        const [values, setValues] = useUrlStateObject(defaults);
        const [searchParams] = useSearchParams();
        return { values, setValues, searchParams };
      },
      { wrapper: createWrapper('/page?status=active') }
    );

    act(() => {
      result.current.setValues({
        status: 'all', // Back to default
      });
    });

    expect(result.current.searchParams.has('status')).toBe(false);
  });
});
