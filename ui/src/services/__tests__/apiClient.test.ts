import { describe, it, expect } from 'vitest';

import { extractApiErrorMessage } from '../apiClient';

const PROBLEM_TYPE = 'about:blank';

describe('extractApiErrorMessage', () => {
  describe('RFC 9457 Problem Details (current backend format)', () => {
    it('should extract detail string from problem response', () => {
      const error = {
        response: {
          status: 404,
          data: {
            type: PROBLEM_TYPE,
            title: 'Not Found',
            status: 404,
            detail: 'Task abc-123 not found',
            request_id: 'd385675e-2a22-492b-a37a-123366177a29',
          },
        },
      };
      expect(extractApiErrorMessage(error)).toBe('Task abc-123 not found');
    });

    it('should extract validation errors from errors array (422)', () => {
      const error = {
        response: {
          status: 422,
          data: {
            type: PROBLEM_TYPE,
            title: 'Validation Error',
            status: 422,
            detail: 'Request validation failed',
            request_id: 'abc-123',
            errors: [
              { loc: ['body', 'name'], msg: 'Field required', type: 'missing' },
              {
                loc: ['body', 'script'],
                msg: 'String should have at least 1 character',
                type: 'string_too_short',
              },
            ],
          },
        },
      };
      expect(extractApiErrorMessage(error)).toBe(
        'Field required, String should have at least 1 character'
      );
    });

    it('should prefer errors array over detail string for 422', () => {
      const error = {
        response: {
          status: 422,
          data: {
            detail: 'Request validation failed',
            errors: [{ msg: 'name is required' }],
          },
        },
      };
      // errors array takes precedence over detail string
      expect(extractApiErrorMessage(error)).toBe('name is required');
    });

    it('should handle 409 conflict', () => {
      const error = {
        response: {
          status: 409,
          data: {
            type: PROBLEM_TYPE,
            title: 'Conflict',
            status: 409,
            detail: 'Integration ID already exists',
            request_id: 'abc-123',
          },
        },
      };
      expect(extractApiErrorMessage(error)).toBe('Integration ID already exists');
    });

    it('should handle 503 database error', () => {
      const error = {
        response: {
          status: 503,
          data: {
            type: PROBLEM_TYPE,
            title: 'Service Unavailable',
            status: 503,
            detail: 'Database temporarily unavailable. Please retry.',
            request_id: 'abc-123',
          },
        },
      };
      expect(extractApiErrorMessage(error)).toBe('Database temporarily unavailable. Please retry.');
    });

    it('should handle 500 internal error', () => {
      const error = {
        response: {
          status: 500,
          data: {
            type: PROBLEM_TYPE,
            title: 'Internal Server Error',
            status: 500,
            detail: 'Internal server error',
            request_id: 'abc-123',
          },
        },
      };
      expect(extractApiErrorMessage(error)).toBe('Internal server error');
    });

    it('should fall back to title when detail is missing', () => {
      const error = {
        response: {
          status: 403,
          data: {
            type: PROBLEM_TYPE,
            title: 'Forbidden',
            status: 403,
            request_id: 'abc-123',
          },
        },
      };
      expect(extractApiErrorMessage(error)).toBe('Forbidden');
    });

    it('should handle empty errors array gracefully', () => {
      const error = {
        response: {
          status: 422,
          data: {
            detail: 'Validation failed',
            errors: [],
          },
        },
      };
      // Empty errors array falls through to detail string
      expect(extractApiErrorMessage(error)).toBe('Validation failed');
    });

    it('should handle errors with message instead of msg', () => {
      const error = {
        response: {
          status: 422,
          data: {
            errors: [{ message: 'Invalid email format' }, { msg: 'Name too long' }],
          },
        },
      };
      expect(extractApiErrorMessage(error)).toBe('Invalid email format, Name too long');
    });
  });

  describe('legacy FastAPI format (backward compatibility)', () => {
    it('should handle detail as string', () => {
      const error = {
        response: { data: { detail: 'Not found' } },
      };
      expect(extractApiErrorMessage(error)).toBe('Not found');
    });

    it('should handle detail as array of validation errors', () => {
      const error = {
        response: {
          data: {
            detail: [
              { msg: 'Field is required', loc: ['body', 'name'] },
              { message: 'Invalid format' },
            ],
          },
        },
      };
      expect(extractApiErrorMessage(error)).toBe('Field is required, Invalid format');
    });

    it('should handle detail as object with msg', () => {
      const error = {
        response: { data: { detail: { msg: 'Validation failed' } } },
      };
      expect(extractApiErrorMessage(error)).toBe('Validation failed');
    });

    it('should handle detail as object with message', () => {
      const error = {
        response: { data: { detail: { message: 'Request failed' } } },
      };
      expect(extractApiErrorMessage(error)).toBe('Request failed');
    });
  });

  describe('network and non-API errors', () => {
    it('should extract message from standard Error', () => {
      const error = { message: 'Network Error' };
      expect(extractApiErrorMessage(error)).toBe('Network Error');
    });

    it('should extract message from AxiosError without response', () => {
      const error = { message: 'timeout of 5000ms exceeded', code: 'ECONNABORTED' };
      expect(extractApiErrorMessage(error)).toBe('timeout of 5000ms exceeded');
    });

    it('should use fallback for null/undefined error', () => {
      expect(extractApiErrorMessage(null, 'Something went wrong')).toBe('Something went wrong');
      expect(extractApiErrorMessage(undefined, 'Something went wrong')).toBe(
        'Something went wrong'
      );
    });

    it('should use fallback for empty object', () => {
      expect(extractApiErrorMessage({}, 'Failed')).toBe('Failed');
    });

    it('should use fallback for error with empty response data', () => {
      const error = { response: { data: {} } };
      expect(extractApiErrorMessage(error, 'Oops')).toBe('Oops');
    });

    it('should use default fallback message', () => {
      expect(extractApiErrorMessage({})).toBe('An error occurred');
    });
  });
});
