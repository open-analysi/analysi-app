/**
 * Extracts total minutes from a time string format like "5h 23m" or "45m"
 *
 * @param timeStr The time string to parse
 * @returns The total number of minutes
 *
 * Examples:
 * - "5h 23m" => 323 (5*60 + 23)
 * - "45m" => 45
 * - "2h" => 120
 * - "" => 0
 */
export const getMinutes = (timeStr: string): number => {
  let totalMinutes = 0;
  // eslint-disable-next-line sonarjs/slow-regex -- simple \d+h pattern, no backtracking risk
  const hoursMatch = /(\d+)h/.exec(timeStr);
  // eslint-disable-next-line sonarjs/slow-regex -- simple \d+m pattern, no backtracking risk
  const minutesMatch = /(\d+)m/.exec(timeStr);

  if (hoursMatch) totalMinutes += Number.parseInt(hoursMatch[1], 10) * 60;
  if (minutesMatch) totalMinutes += Number.parseInt(minutesMatch[1], 10);

  return totalMinutes;
};
