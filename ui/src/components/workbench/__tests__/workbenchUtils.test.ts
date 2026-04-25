import { describe, it, expect } from 'vitest';

import {
  ADHOC_DRAFT_KEY,
  DEFAULT_SCRIPT,
  parseErrorLocation,
  generateVersionedName,
  getToolNamespaceClasses,
  getStatusClasses,
  parseExecutionOutput,
  parseTaskRunInput,
} from '../workbenchUtils';

// ─── Constants ───────────────────────────────────────────────────────

describe('constants', () => {
  it('ADHOC_DRAFT_KEY has expected value', () => {
    expect(ADHOC_DRAFT_KEY).toBe('__adhoc__');
  });

  it('DEFAULT_SCRIPT has expected value', () => {
    expect(DEFAULT_SCRIPT).toBe('return "Hello World"');
  });
});

// ─── parseErrorLocation ──────────────────────────────────────────────

describe('parseErrorLocation', () => {
  it('returns null for empty input', () => {
    expect(parseErrorLocation('')).toBeNull();
  });

  it('returns null for non-error output', () => {
    expect(parseErrorLocation('Task completed successfully')).toBeNull();
  });

  it('parses compilation error format (Line X, Col Y)', () => {
    const result = parseErrorLocation(
      "Line 2, Col 1: Unexpected token Token('$END', '') at line 2, column 1"
    );
    expect(result).toEqual({
      line: 2,
      column: 1,
      message: "Unexpected token Token('$END', '') at line 2, column 1",
    });
  });

  it('parses runtime error format (Line X, Column Y)', () => {
    const result = parseErrorLocation(
      "Line 2, Column 10: Tool 'app::nonexistent::fake_action' not found"
    );
    expect(result).toEqual({
      line: 2,
      column: 10,
      message: "Tool 'app::nonexistent::fake_action' not found",
    });
  });

  it('parses JSON-wrapped errors', () => {
    const jsonOutput = JSON.stringify({
      error: "Line 5, Col 3: Invalid syntax near 'if'",
    });
    const result = parseErrorLocation(jsonOutput);
    expect(result).toEqual({
      line: 5,
      column: 3,
      message: "Invalid syntax near 'if'",
    });
  });

  it('falls back to raw text when JSON has non-string error', () => {
    const jsonOutput = JSON.stringify({ error: 42 });
    // No Line X, Col Y in the JSON output itself
    expect(parseErrorLocation(jsonOutput)).toBeNull();
  });

  it('handles case-insensitive matching', () => {
    const result = parseErrorLocation('line 10, column 5: Something went wrong');
    expect(result).toEqual({
      line: 10,
      column: 5,
      message: 'Something went wrong',
    });
  });

  it('trims whitespace from message', () => {
    const result = parseErrorLocation('Line 1, Col 1:   extra spaces   ');
    expect(result?.message).toBe('extra spaces');
  });
});

// ─── generateVersionedName ───────────────────────────────────────────

describe('generateVersionedName', () => {
  it('appends v2 to a name without version', () => {
    expect(generateVersionedName('My Task')).toBe('My Task v2');
  });

  it('increments v2 to v3', () => {
    expect(generateVersionedName('My Task v2')).toBe('My Task v3');
  });

  it('increments v9 to v10', () => {
    expect(generateVersionedName('My Task v9')).toBe('My Task v10');
  });

  it('does not match v in the middle of a word', () => {
    expect(generateVersionedName('Move v2 Data')).toBe('Move v2 Data v2');
  });

  it('handles empty string', () => {
    expect(generateVersionedName('')).toBe(' v2');
  });
});

// ─── getToolNamespaceClasses ─────────────────────────────────────────

describe('getToolNamespaceClasses', () => {
  it('returns blue classes for "app" namespace', () => {
    const classes = getToolNamespaceClasses('app');
    expect(classes).toContain('blue');
  });

  it('returns purple classes for "native" namespace', () => {
    const classes = getToolNamespaceClasses('native');
    expect(classes).toContain('purple');
  });

  it('returns gray classes for other namespaces', () => {
    const classes = getToolNamespaceClasses('str');
    expect(classes).toContain('gray');
  });

  it('returns gray classes for unknown namespace', () => {
    const classes = getToolNamespaceClasses('custom');
    expect(classes).toContain('gray');
  });
});

// ─── getStatusClasses ────────────────────────────────────────────────

describe('getStatusClasses', () => {
  it('returns green for completed', () => {
    expect(getStatusClasses('completed')).toContain('green');
  });

  it('returns red for failed', () => {
    expect(getStatusClasses('failed')).toContain('red');
  });

  it('returns gray for other statuses', () => {
    expect(getStatusClasses('running')).toContain('gray');
  });
});

// ─── parseExecutionOutput ────────────────────────────────────────────

describe('parseExecutionOutput', () => {
  it('parses inline JSON output', () => {
    const result = parseExecutionOutput({
      output_type: 'inline',
      output_location: '{"result": "success"}',
    });
    expect(result.output).toEqual({ result: 'success' });
  });

  it('returns message for null output_type', () => {
    const result = parseExecutionOutput({
      output_type: null,
      output_location: '',
    });
    expect(result.output).toEqual({ message: 'No output captured' });
  });

  it('returns error for S3 output_type', () => {
    const result = parseExecutionOutput({
      output_type: 's3',
      output_location: 's3://bucket/key',
    });
    expect(result.output).toEqual({ error: 'S3 storage not yet supported in UI' });
  });

  it('handles invalid JSON in inline output', () => {
    const result = parseExecutionOutput({
      output_type: 'inline',
      output_location: 'not valid json',
    });
    expect(result.output).toEqual({
      error: 'Failed to parse output',
      raw_output: 'not valid json',
    });
  });
});

// ─── parseTaskRunInput ──────────────────────────────────────────────

describe('parseTaskRunInput', () => {
  it('returns empty string for non-inline input type', () => {
    expect(parseTaskRunInput('s3', 's3://bucket/key')).toBe('');
  });

  it('returns empty string when input_type is null', () => {
    expect(parseTaskRunInput(null, '{"key": "value"}')).toBe('');
  });

  it('returns empty string when input_location is null', () => {
    expect(parseTaskRunInput('inline', null)).toBe('');
  });

  it('returns empty string when called with no arguments', () => {
    expect(parseTaskRunInput()).toBe('');
  });

  it('passes through string values from JSON', () => {
    expect(parseTaskRunInput('inline', '"hello world"')).toBe('hello world');
  });

  it('pretty-prints object values from JSON', () => {
    const input = JSON.stringify({ alert_id: '123', severity: 'high' });
    const result = parseTaskRunInput('inline', input);
    expect(result).toBe(JSON.stringify({ alert_id: '123', severity: 'high' }, null, 2));
  });

  it('returns raw string for invalid JSON', () => {
    expect(parseTaskRunInput('inline', 'not valid json')).toBe('not valid json');
  });

  it('pretty-prints array values from JSON', () => {
    const input = JSON.stringify([1, 2, 3]);
    const result = parseTaskRunInput('inline', input);
    expect(result).toBe(JSON.stringify([1, 2, 3], null, 2));
  });
});
