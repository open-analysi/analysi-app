/**
 * Client-side alert schema validation.
 *
 * Mirrors the MCP schema_tools.validate_alert logic so the CLI
 * can validate alerts without a server-side endpoint.
 */

export interface ValidationError {
  field: string
  message: string
  error_type: string
}

export interface ValidationResult {
  valid: boolean
  errors: ValidationError[]
  warnings: ValidationError[]
  alert_structure: {
    field_count: number
    has_required_fields: boolean
  }
}

const REQUIRED_FIELDS = new Set(['title', 'triggering_event_time', 'severity', 'raw_alert'])

const OPTIONAL_FIELDS = new Set([
  'source_vendor', 'source_product', 'source_category', 'rule_name',
  'alert_type', 'action', 'primary_risk_entity_value',
  'primary_risk_entity_type', 'primary_ioc_value', 'primary_ioc_type',
  'risk_entities', 'iocs', 'source_event_id', 'network_info',
  'web_info', 'process_info', 'cve_info', 'other_activities', 'detected_at',
])

const VALID_SEVERITIES = ['critical', 'high', 'medium', 'low', 'info']

/**
 * Validate an alert object against the alert schema.
 * Returns errors for required fields, bad enums, bad timestamps.
 * Returns warnings for extra non-standard fields.
 */
export function validateAlert(data: Record<string, unknown>): ValidationResult {
  const errors: ValidationError[] = []
  const warnings: ValidationError[] = []

  // Check missing required fields
  for (const field of REQUIRED_FIELDS) {
    if (!(field in data)) {
      errors.push({
        field,
        message: `Required field '${field}' is missing`,
        error_type: 'missing_required',
      })
    }
  }

  // Check extra fields
  for (const field of Object.keys(data)) {
    if (!REQUIRED_FIELDS.has(field) && !OPTIONAL_FIELDS.has(field)) {
      warnings.push({
        field,
        message: `Non-standard field '${field}' is not part of the alert schema`,
        error_type: 'extra_field',
      })
    }
  }

  // Validate required string fields (title, raw_alert)
  for (const field of ['title', 'raw_alert']) {
    if (field in data && typeof data[field] !== 'string') {
      errors.push({
        field,
        message: `Field '${field}' must be a string, got ${typeof data[field]}`,
        error_type: 'invalid_type',
      })
    }
  }

  // Validate severity
  if ('severity' in data) {
    if (typeof data.severity !== 'string') {
      errors.push({
        field: 'severity',
        message: `Field 'severity' must be a string, got ${typeof data.severity}`,
        error_type: 'invalid_type',
      })
    } else if (!VALID_SEVERITIES.includes(data.severity)) {
      errors.push({
        field: 'severity',
        message: `Invalid severity '${data.severity}'. Must be one of: ${VALID_SEVERITIES.join(', ')}`,
        error_type: 'invalid_enum',
      })
    }
  }

  // Validate timestamp fields
  for (const field of ['triggering_event_time', 'detected_at']) {
    if (!(field in data)) continue

    if (typeof data[field] !== 'string') {
      errors.push({
        field,
        message: `Field '${field}' must be a string in ISO format, got ${typeof data[field]}`,
        error_type: 'invalid_type',
      })
      continue
    }

    const val = data[field] as string
    if (!val.includes('T') || (!val.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(val))) {
      errors.push({
        field,
        message: 'Invalid datetime format. Expected ISO 8601 (e.g., 2026-01-01T00:00:00Z)',
        error_type: 'invalid_format',
      })
    } else if (!isValidTimezoneOffset(val)) {
      errors.push({
        field,
        message: 'Invalid timezone offset. Must be Z or ±HH:MM where HH ≤ 14 and MM ≤ 59',
        error_type: 'invalid_format',
      })
    } else if (!isValidDatetime(val)) {
      errors.push({
        field,
        message: 'Invalid datetime value. The date/time components are out of range',
        error_type: 'invalid_format',
      })
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    alert_structure: {
      field_count: Object.keys(data).length,
      has_required_fields: [...REQUIRED_FIELDS].every((f) => f in data),
    },
  }
}

/**
 * Validate timezone offset bounds (ISO 8601 allows ±00:00 to ±14:00).
 * Returns true for 'Z' suffix or valid ±HH:MM within range.
 */
function isValidTimezoneOffset(val: string): boolean {
  if (val.endsWith('Z')) return true
  const tzMatch = val.match(/([+-])(\d{2}):(\d{2})$/)
  if (!tzMatch) return false
  const tzHour = parseInt(tzMatch[2], 10)
  const tzMin = parseInt(tzMatch[3], 10)
  if (tzHour > 14 || tzMin > 59) return false
  // +14:00 is the max; offsets like +14:30 are invalid
  if (tzHour === 14 && tzMin > 0) return false
  return true
}

/**
 * Strict datetime validation — rejects values that Date.parse silently rolls over
 * (e.g., Feb 29 in non-leap year, month 13, day 32).
 *
 * Extracts Y/M/D/h/m/s from the string, constructs a UTC Date, and verifies the
 * components round-trip without rollover.
 */
function isValidDatetime(val: string): boolean {
  // Full ISO 8601 pattern anchored end-to-end — rejects junk between seconds and timezone
  const match = val.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/)
  if (!match) return false

  const [, ys, ms, ds, hs, mins, ss] = match
  const year = parseInt(ys, 10)
  const month = parseInt(ms, 10)
  const day = parseInt(ds, 10)
  const hour = parseInt(hs, 10)
  const minute = parseInt(mins, 10)
  const second = parseInt(ss, 10)

  // Range checks
  if (month < 1 || month > 12) return false
  if (day < 1 || day > 31) return false
  if (hour > 23 || minute > 59 || second > 59) return false

  // Construct UTC date and check for rollover (catches Feb 29 in non-leap years, etc.)
  const d = new Date(Date.UTC(year, month - 1, day))
  return d.getUTCFullYear() === year && d.getUTCMonth() + 1 === month && d.getUTCDate() === day
}
