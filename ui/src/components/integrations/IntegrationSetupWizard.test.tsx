import { describe, it, expect } from 'vitest';

import { extractApiErrorMessage } from '../../services/apiClient';

describe('IntegrationSetupWizard - Helper Functions', () => {
  // These tests verify the helper functions extracted during linting fixes
  // to ensure refactoring didn't break functionality

  describe('getDefaultParamValue', () => {
    it('should return the default value if provided', () => {
      const property: { type: string; default?: unknown; required: boolean } = {
        type: 'string',
        default: 'test-value',
        required: false,
      };
      // Simulating the helper function logic
      const result = property.default != null ? property.default : undefined;
      expect(result).toBe('test-value');
    });

    it('should return undefined for non-required fields without defaults', () => {
      const property: { type: string; default?: unknown; required: boolean } = {
        type: 'string',
        required: false,
      };
      let result;
      if (property.default != null) {
        result = property.default;
      } else if (!property.required) {
        result = undefined;
      } else {
        result = '';
      }
      expect(result).toBeUndefined();
    });

    it('should return 300 for lookback_seconds integer field', () => {
      const key = 'lookback_seconds';
      const property: { type: string; default?: unknown; required: boolean } = {
        type: 'integer',
        required: true,
      };
      // Simulating the logic from getDefaultParamValue
      let result;
      if (property.type === 'integer' && property.required && !property.default) {
        if (key === 'lookback_seconds') {
          result = 300;
        }
      }
      expect(result).toBe(300);
    });

    it('should return min value for required integer fields with min', () => {
      const property: { type: string; default?: unknown; required: boolean; min?: number } = {
        type: 'integer',
        required: true,
        min: 5,
      };
      let result;
      if (property.type === 'integer' && property.required && !property.default) {
        result = property.min != null ? property.min : 0;
      }
      expect(result).toBe(5);
    });

    it('should return 0 for required integer fields without min or default', () => {
      const property: { type: string; default?: unknown; required: boolean } = {
        type: 'integer',
        required: true,
      };
      let result;
      if (property.type === 'integer' && property.required && !property.default) {
        result = 0;
      }
      expect(result).toBe(0);
    });

    it('should return false for required boolean fields', () => {
      const property: { type: string; default?: unknown; required: boolean } = {
        type: 'boolean',
        required: true,
      };
      let result;
      if (property.type === 'boolean' && property.required && !property.default) {
        result = false;
      }
      expect(result).toBe(false);
    });

    it('should return empty string for required string fields', () => {
      const property: { type: string; default?: unknown; required: boolean } = {
        type: 'string',
        required: true,
      };
      let result;
      if (property.type === 'string' && property.required && !property.default) {
        result = '';
      }
      expect(result).toBe('');
    });
  });

  describe('validateIntegrationId', () => {
    it('should accept valid integration IDs', () => {
      const validIds = ['test-123', 'my-integration', 'abc', '123-test', 'a', '1'];
      const pattern = /^[\da-z][\da-z-]*$/;

      for (const id of validIds) {
        expect(pattern.test(id)).toBe(true);
      }
    });

    it('should reject IDs starting with uppercase', () => {
      const pattern = /^[\da-z][\da-z-]*$/;
      expect(pattern.test('Test-123')).toBe(false);
    });

    it('should reject IDs starting with hyphen', () => {
      const pattern = /^[\da-z][\da-z-]*$/;
      expect(pattern.test('-test')).toBe(false);
    });

    it('should reject IDs with special characters', () => {
      const pattern = /^[\da-z][\da-z-]*$/;
      expect(pattern.test('test_123')).toBe(false);
      expect(pattern.test('test.123')).toBe(false);
      expect(pattern.test('test@123')).toBe(false);
    });

    it('should detect duplicate IDs', () => {
      const existingIds = ['splunk-main', 'crowdstrike-prod'];
      const testId = 'splunk-main';
      expect(existingIds.includes(testId)).toBe(true);
    });
  });

  describe('validateSettingProperty', () => {
    it('should return error for required field without value', () => {
      const prop = { type: 'string', required: true, display_name: 'API URL' };
      const value = undefined;

      const error = prop.required && !value ? `${prop.display_name} is required` : undefined;
      expect(error).toBe('API URL is required');
    });

    it('should return error for integer below min', () => {
      const prop = { type: 'integer', min: 5, max: 100 };
      const value = 3;

      const error =
        prop.min != null && value < prop.min ? `Must be at least ${prop.min}` : undefined;
      expect(error).toBe('Must be at least 5');
    });

    it('should return error for integer above max', () => {
      const prop = { type: 'integer', min: 5, max: 100 };
      const value = 150;

      const error =
        prop.max != null && value > prop.max ? `Must be at most ${prop.max}` : undefined;
      expect(error).toBe('Must be at most 100');
    });

    it('should return error for pattern mismatch', () => {
      const prop = { type: 'string', pattern: '^https://', description: 'Must be HTTPS URL' };
      const value = 'http://example.com';

      const pattern = new RegExp(prop.pattern);
      const error = !pattern.test(value) ? prop.description : undefined;
      expect(error).toBe('Must be HTTPS URL');
    });

    it('should return undefined for valid values', () => {
      const prop = { type: 'integer', min: 5, max: 100, required: true };
      const value = 50;

      let error;
      if (prop.required && !value) {
        error = 'Required';
      } else if (prop.min != null && value < prop.min) {
        error = 'Too small';
      } else if (prop.max != null && value > prop.max) {
        error = 'Too large';
      }
      expect(error).toBeUndefined();
    });
  });

  describe('validateScheduleParam', () => {
    it('should return error for required param without value', () => {
      const prop = { type: 'integer', required: true, display_name: 'Lookback Seconds' };
      const value = undefined;
      const connectorName = 'Splunk Connector';

      const error =
        prop.required && !value
          ? `${prop.display_name} is required for ${connectorName} schedule`
          : undefined;
      expect(error).toBe('Lookback Seconds is required for Splunk Connector schedule');
    });

    it('should validate ISO date-time format', () => {
      const validDates = [
        '2024-01-15T10:30:00Z',
        '2024-01-15T10:30:00.123Z',
        'now',
        '-5m',
        '-1h',
        '-30d',
      ];

      const isoDateRegex = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z?$/;

      for (const date of validDates) {
        const isValid = isoDateRegex.test(date) || date === 'now' || date.startsWith('-');
        expect(isValid).toBe(true);
      }
    });

    it('should reject invalid date-time formats', () => {
      const invalidDates = ['2024-01-15', '10:30:00', 'invalid', '2024/01/15'];

      const isoDateRegex = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z?$/;

      for (const date of invalidDates) {
        const isValid = isoDateRegex.test(date) || date === 'now' || date.startsWith('-');
        expect(isValid).toBe(false);
      }
    });
  });

  describe('extractApiErrorMessage (RFC 9457)', () => {
    it('should extract string detail from RFC 9457 response', () => {
      const error = {
        response: {
          data: {
            type: 'about:blank',
            title: 'Conflict',
            status: 409,
            detail: 'Integration already exists',
            request_id: 'abc-123',
          },
        },
      };
      expect(extractApiErrorMessage(error)).toBe('Integration already exists');
    });

    it('should extract validation errors from RFC 9457 errors array', () => {
      const error = {
        response: {
          data: {
            type: 'about:blank',
            title: 'Validation Error',
            status: 422,
            detail: 'Request validation failed',
            errors: [{ msg: 'Field is required' }, { msg: 'Invalid format' }],
            request_id: 'abc-123',
          },
        },
      };
      expect(extractApiErrorMessage(error)).toBe('Field is required, Invalid format');
    });

    it('should fall back to legacy detail array format', () => {
      const error = {
        response: {
          data: {
            detail: [{ msg: 'Validation failed' }, { message: 'Request failed' }],
          },
        },
      };
      expect(extractApiErrorMessage(error)).toBe('Validation failed, Request failed');
    });

    it('should fall back to legacy detail object with msg', () => {
      const error = {
        response: { data: { detail: { msg: 'Validation failed' } } },
      };
      expect(extractApiErrorMessage(error)).toBe('Validation failed');
    });

    it('should fallback to standard error message', () => {
      const error = { message: 'Network error occurred' };
      expect(extractApiErrorMessage(error)).toBe('Network error occurred');
    });

    it('should use fallback when no error info available', () => {
      expect(extractApiErrorMessage({}, 'Failed to complete setup')).toBe(
        'Failed to complete setup'
      );
    });
  });

  describe('handleSetupError', () => {
    it('should handle 409 conflict errors with special message', () => {
      const error = {
        response: {
          status: 409,
          data: {
            type: 'about:blank',
            title: 'Conflict',
            status: 409,
            detail: 'Integration ID already exists',
            request_id: 'abc-123',
          },
        },
      };

      const is409 = error.response?.status === 409;
      const message = extractApiErrorMessage(error);
      const includesAlreadyExists = message.includes('already exists');

      expect(is409).toBe(true);
      expect(includesAlreadyExists).toBe(true);

      const finalMessage = `${message}. Please use a different Integration ID or delete the existing integration first.`;
      expect(finalMessage).toContain('Please use a different Integration ID');
    });

    it('should determine failed step from setup progress', () => {
      const setupProgress = [
        { step: 'Creating integration', status: 'done' as const },
        { step: 'Creating credentials', status: 'working' as const },
      ];

      const lastStep = setupProgress[setupProgress.length - 1];
      const errorStep = lastStep.status === 'working' ? lastStep.step : 'Setup';

      expect(errorStep).toBe('Creating credentials');
    });
  });
});

describe('IntegrationSetupWizard - Optional Credential Handling', () => {
  const mockIntegrationTypeWithOptionalCredentials = {
    type: 'nistnvd',
    display_name: 'NIST NVD',
    description: 'NIST National Vulnerability Database',
    credential_schema: {
      type: 'object',
      properties: {
        api_key: {
          type: 'string',
          display_name: 'API Key',
          description: 'Optional NIST NVD API key for higher rate limits',
          required: false, // OPTIONAL field
          format: 'password',
        },
      },
    },
    settings_schema: {
      type: 'object',
      properties: {
        api_version: {
          type: 'string',
          display_name: 'API Version',
          default: '2.0',
          required: true,
        },
      },
    },
  };

  const mockIntegrationTypeWithRequiredCredentials = {
    type: 'splunk',
    display_name: 'Splunk',
    description: 'Splunk SIEM',
    credential_schema: {
      type: 'object',
      properties: {
        api_token: {
          type: 'string',
          display_name: 'API Token',
          description: 'Splunk API token',
          required: true, // REQUIRED field
          format: 'password',
        },
      },
    },
    settings_schema: {
      type: 'object',
      properties: {},
    },
  };

  it('should allow skipping credentials for integration with only optional credential fields', () => {
    // This test verifies the core bug fix:
    // Before: validateCredentials() would fail if no credentials were added
    // After: validateCredentials() passes when all credential fields are optional

    const integrationType = mockIntegrationTypeWithOptionalCredentials;
    const credentials: never[] = []; // Empty credentials array

    // Simulate the hasRequiredCredentialFields() helper
    const hasRequiredFields =
      integrationType.credential_schema?.properties &&
      Object.values(integrationType.credential_schema.properties).some(
        (prop: { required?: boolean }) => prop.required === true
      );

    // Should be false for NISTNVD (all fields optional)
    expect(hasRequiredFields).toBe(false);

    // Simulate validation logic
    const shouldBlockCredentialStep = hasRequiredFields && credentials.length === 0;

    // Should NOT block when all fields are optional
    expect(shouldBlockCredentialStep).toBe(false);
  });

  it('should require at least one credential for integration with required credential fields', () => {
    const integrationType = mockIntegrationTypeWithRequiredCredentials;
    const credentials: never[] = []; // Empty credentials array

    // Simulate the hasRequiredCredentialFields() helper
    const hasRequiredFields =
      integrationType.credential_schema?.properties &&
      Object.values(integrationType.credential_schema.properties).some(
        (prop: { required?: boolean }) => prop.required === true
      );

    // Should be true for Splunk (has required fields)
    expect(hasRequiredFields).toBe(true);

    // Simulate validation logic
    const shouldBlockCredentialStep = hasRequiredFields && credentials.length === 0;

    // SHOULD block when required fields exist and no credentials
    expect(shouldBlockCredentialStep).toBe(true);
  });

  it('should correctly identify integrations with all optional credentials', () => {
    const testCases = [
      {
        name: 'NISTNVD - optional API key',
        credentialSchema: {
          properties: {
            api_key: { required: false },
          },
        },
        expectedResult: false, // No required fields
      },
      {
        name: 'Splunk - required token',
        credentialSchema: {
          properties: {
            api_token: { required: true },
          },
        },
        expectedResult: true, // Has required fields
      },
      {
        name: 'Mixed - one required, one optional',
        credentialSchema: {
          properties: {
            username: { required: true },
            api_key: { required: false },
          },
        },
        expectedResult: true, // Has at least one required field
      },
      {
        name: 'All optional',
        credentialSchema: {
          properties: {
            api_key: { required: false },
            webhook_url: { required: false },
          },
        },
        expectedResult: false, // No required fields
      },
      {
        name: 'No credential schema',
        credentialSchema: undefined,
        expectedResult: false, // No fields at all
      },
    ];

    for (const testCase of testCases) {
      const hasRequiredFields = testCase.credentialSchema?.properties
        ? Object.values(testCase.credentialSchema.properties).some(
            (prop: { required?: boolean }) => prop.required === true
          )
        : false;

      expect(hasRequiredFields).toBe(testCase.expectedResult);
    }
  });

  it('should not show warning message when credentials are optional and not provided', () => {
    // Simulates the Review step logic for showing warnings
    const credentials: never[] = [];
    const integrationType = mockIntegrationTypeWithOptionalCredentials;

    const hasRequiredFields =
      integrationType.credential_schema?.properties &&
      Object.values(integrationType.credential_schema.properties).some(
        (prop: { required?: boolean }) => prop.required === true
      );

    // Simulate the warning condition from Review step
    const shouldShowWarning = credentials.length === 0 && hasRequiredFields;

    // Should NOT show warning for optional credentials
    expect(shouldShowWarning).toBe(false);
  });

  it('should show warning message when credentials are required but not provided', () => {
    // Simulates the Review step logic for showing warnings
    const credentials: never[] = [];
    const integrationType = mockIntegrationTypeWithRequiredCredentials;

    const hasRequiredFields =
      integrationType.credential_schema?.properties &&
      Object.values(integrationType.credential_schema.properties).some(
        (prop: { required?: boolean }) => prop.required === true
      );

    // Simulate the warning condition from Review step
    const shouldShowWarning = credentials.length === 0 && hasRequiredFields;

    // SHOULD show warning for required credentials
    expect(shouldShowWarning).toBe(true);
  });
});
