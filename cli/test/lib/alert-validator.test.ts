/**
 * Unit tests for NAS validator — client-side alert validation.
 *
 * Covers use cases:
 *   UC38:  Valid alert passes
 *   UC38b: Invalid alert (missing fields, bad severity, extra fields)
 *   UC38c: JSON output shape
 *   UC51:  Bad timestamp format
 *   UC52:  Multiple errors + warnings
 */

import { describe, it, expect } from 'vitest'
import { validateAlert } from '../../src/lib/alert-validator.js'

const VALID_ALERT = {
  title: 'Test Alert',
  severity: 'high',
  triggering_event_time: '2026-03-15T10:00:00Z',
  raw_alert: 'raw data here',
}

describe('validateAlert — valid alerts', () => {
  it('passes a minimal valid alert (UC38)', () => {
    const result = validateAlert(VALID_ALERT)
    expect(result.valid).toBe(true)
    expect(result.errors).toHaveLength(0)
    expect(result.warnings).toHaveLength(0)
    expect(result.alert_structure.field_count).toBe(4)
    expect(result.alert_structure.has_required_fields).toBe(true)
  })

  it('passes with optional fields present', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      source_vendor: 'Splunk',
      source_product: 'Enterprise',
      rule_name: 'Detection-1',
    })
    expect(result.valid).toBe(true)
    expect(result.alert_structure.field_count).toBe(7)
  })

  it('accepts all valid severity values', () => {
    for (const sev of ['critical', 'high', 'medium', 'low', 'info']) {
      const result = validateAlert({ ...VALID_ALERT, severity: sev })
      expect(result.valid, `severity=${sev} should be valid`).toBe(true)
    }
  })

  it('accepts UTC offset timezone (+05:30)', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2026-03-15T10:00:00+05:30',
    })
    expect(result.valid).toBe(true)
  })

  it('accepts negative UTC offset timezone (-08:00)', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2026-03-15T10:00:00-08:00',
    })
    expect(result.valid).toBe(true)
  })

  it('accepts max valid offset (+14:00)', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2026-03-15T10:00:00+14:00',
    })
    expect(result.valid).toBe(true)
  })

  it('errors on impossible timezone offset (+25:00)', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2026-03-15T10:00:00+25:00',
    })
    expect(result.valid).toBe(false)
    expect(result.errors[0].error_type).toBe('invalid_format')
  })

  it('errors on impossible timezone offset (+99:99)', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2026-03-15T10:00:00+99:99',
    })
    expect(result.valid).toBe(false)
  })

  it('errors on offset exceeding +14:00 (+14:30)', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2026-03-15T10:00:00+14:30',
    })
    expect(result.valid).toBe(false)
  })

  it('errors on junk between seconds and timezone suffix', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2026-03-15T10:00:00junkZ',
    })
    expect(result.valid).toBe(false)
    expect(result.errors[0].error_type).toBe('invalid_format')
  })

  it('accepts fractional seconds', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2026-03-15T10:00:00.123Z',
    })
    expect(result.valid).toBe(true)
  })
})

describe('validateAlert — missing required fields (UC38b)', () => {
  it('errors on empty object (all 4 required fields missing)', () => {
    const result = validateAlert({})
    expect(result.valid).toBe(false)
    expect(result.errors).toHaveLength(4)
    const fields = result.errors.map((e) => e.field).sort()
    expect(fields).toEqual(['raw_alert', 'severity', 'title', 'triggering_event_time'])
    expect(result.errors.every((e) => e.error_type === 'missing_required')).toBe(true)
  })

  it('errors on missing single required field', () => {
    const { raw_alert, ...partial } = VALID_ALERT
    const result = validateAlert(partial)
    expect(result.valid).toBe(false)
    expect(result.errors).toHaveLength(1)
    expect(result.errors[0].field).toBe('raw_alert')
  })
})

describe('validateAlert — required field type checking', () => {
  it('errors on non-string title', () => {
    const result = validateAlert({ ...VALID_ALERT, title: 123 })
    expect(result.valid).toBe(false)
    expect(result.errors.find((e) => e.field === 'title')?.error_type).toBe('invalid_type')
  })

  it('errors on non-string raw_alert', () => {
    const result = validateAlert({ ...VALID_ALERT, raw_alert: { data: 'x' } })
    expect(result.valid).toBe(false)
    expect(result.errors.find((e) => e.field === 'raw_alert')?.error_type).toBe('invalid_type')
  })

  it('accepts valid string title and raw_alert', () => {
    const result = validateAlert(VALID_ALERT)
    expect(result.errors.filter((e) => e.field === 'title')).toHaveLength(0)
    expect(result.errors.filter((e) => e.field === 'raw_alert')).toHaveLength(0)
  })
})

describe('validateAlert — invalid severity (UC38b)', () => {
  it('errors on uppercase severity', () => {
    const result = validateAlert({ ...VALID_ALERT, severity: 'CRITICAL' })
    expect(result.valid).toBe(false)
    expect(result.errors).toHaveLength(1)
    expect(result.errors[0].field).toBe('severity')
    expect(result.errors[0].error_type).toBe('invalid_enum')
    expect(result.errors[0].message).toContain('CRITICAL')
  })

  it('errors on unknown severity', () => {
    const result = validateAlert({ ...VALID_ALERT, severity: 'urgent' })
    expect(result.valid).toBe(false)
    expect(result.errors[0].message).toContain('urgent')
  })

  it('errors on non-string severity (number)', () => {
    const result = validateAlert({ ...VALID_ALERT, severity: 3 })
    expect(result.valid).toBe(false)
    expect(result.errors[0].error_type).toBe('invalid_type')
    expect(result.errors[0].message).toContain('must be a string')
  })

  it('errors on non-string severity (boolean)', () => {
    const result = validateAlert({ ...VALID_ALERT, severity: true })
    expect(result.valid).toBe(false)
    expect(result.errors[0].error_type).toBe('invalid_type')
  })
})

describe('validateAlert — timestamp validation (UC51)', () => {
  it('errors on date-only (no T separator)', () => {
    const result = validateAlert({ ...VALID_ALERT, triggering_event_time: '2026-03-15' })
    expect(result.valid).toBe(false)
    expect(result.errors[0].field).toBe('triggering_event_time')
    expect(result.errors[0].error_type).toBe('invalid_format')
  })

  it('errors on missing timezone', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2026-03-15T10:00:00',
    })
    expect(result.valid).toBe(false)
    expect(result.errors[0].error_type).toBe('invalid_format')
  })

  it('validates detected_at timestamp too', () => {
    const result = validateAlert({ ...VALID_ALERT, detected_at: '2026-03-15' })
    expect(result.valid).toBe(false)
    expect(result.errors[0].field).toBe('detected_at')
  })

  it('errors on non-string triggering_event_time (number)', () => {
    const result = validateAlert({ ...VALID_ALERT, triggering_event_time: 1234567890 })
    expect(result.valid).toBe(false)
    expect(result.errors[0].error_type).toBe('invalid_type')
    expect(result.errors[0].field).toBe('triggering_event_time')
  })

  it('errors on non-string detected_at (object)', () => {
    const result = validateAlert({ ...VALID_ALERT, detected_at: { date: '2026-03-15' } })
    expect(result.valid).toBe(false)
    expect(result.errors[0].error_type).toBe('invalid_type')
    expect(result.errors[0].field).toBe('detected_at')
  })

  it('errors on impossible datetime values (month 13)', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2026-13-99T25:61:61Z',
    })
    expect(result.valid).toBe(false)
    expect(result.errors[0].field).toBe('triggering_event_time')
    expect(result.errors[0].error_type).toBe('invalid_format')
  })

  it('errors on impossible detected_at value (day 99)', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      detected_at: '2026-01-99T10:00:00Z',
    })
    expect(result.valid).toBe(false)
    expect(result.errors[0].field).toBe('detected_at')
    expect(result.errors[0].error_type).toBe('invalid_format')
  })

  it('errors on Feb 29 in non-leap year (2025)', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2025-02-29T00:00:00Z',
    })
    expect(result.valid).toBe(false)
    expect(result.errors[0].field).toBe('triggering_event_time')
    expect(result.errors[0].error_type).toBe('invalid_format')
  })

  it('accepts Feb 29 in leap year (2024)', () => {
    const result = validateAlert({
      ...VALID_ALERT,
      triggering_event_time: '2024-02-29T00:00:00Z',
    })
    expect(result.valid).toBe(true)
  })
})

describe('validateAlert — extra fields (UC52 warnings)', () => {
  it('warns on unknown fields', () => {
    const result = validateAlert({ ...VALID_ALERT, custom_field: 'oops', another: 123 })
    expect(result.valid).toBe(true) // warnings don't make it invalid
    expect(result.warnings).toHaveLength(2)
    expect(result.warnings.every((w) => w.error_type === 'extra_field')).toBe(true)
  })

  it('does not warn on known optional fields', () => {
    const result = validateAlert({ ...VALID_ALERT, source_vendor: 'Splunk' })
    expect(result.warnings).toHaveLength(0)
  })
})

describe('validateAlert — combined errors (UC52)', () => {
  it('reports multiple errors and warnings together', () => {
    const result = validateAlert({
      severity: 'WRONG',
      extra: 'x',
    })
    expect(result.valid).toBe(false)
    // 3 missing required + 1 bad enum = 4 errors
    expect(result.errors.length).toBeGreaterThanOrEqual(4)
    // 1 extra field warning
    expect(result.warnings).toHaveLength(1)
  })
})

describe('validateAlert — output shape (UC38c)', () => {
  it('always returns the full shape even for valid alerts', () => {
    const result = validateAlert(VALID_ALERT)
    expect(result).toHaveProperty('valid')
    expect(result).toHaveProperty('errors')
    expect(result).toHaveProperty('warnings')
    expect(result).toHaveProperty('alert_structure')
    expect(result.alert_structure).toHaveProperty('field_count')
    expect(result.alert_structure).toHaveProperty('has_required_fields')
  })
})
