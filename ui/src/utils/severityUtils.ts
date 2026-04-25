/**
 * Defines the order of severity levels for sorting
 */
export const severityOrder: Record<string, number> = {
  Critical: 0,
  High: 1,
  Medium: 2,
  Low: 3,
};

/**
 * Gets the numeric order value for a severity string
 *
 * @param severity The severity level string
 * @returns The numeric order (lower is more severe)
 */
export const getSeverityOrder = (severity: string): number => {
  return severityOrder[severity] ?? 999;
};
