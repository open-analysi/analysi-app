export type StatusLevel = 'Critical' | 'High' | 'Medium' | 'Low' | 'Very Low';

/**
 * Returns dark theme color classes for status severity badges.
 * Uses dark backgrounds (900) with light text (300) for optimal contrast on dark-800/dark-900 backgrounds.
 */
export const getStatusColor = (level: string) => {
  switch (level.toLowerCase()) {
    case 'critical': {
      return 'bg-red-900 text-red-300 dark:bg-red-900 dark:text-red-300 font-bold';
    }
    case 'high': {
      return 'bg-orange-900 text-orange-300 dark:bg-orange-900 dark:text-orange-300';
    }
    case 'medium': {
      return 'bg-yellow-900 text-yellow-300 dark:bg-yellow-900 dark:text-yellow-300';
    }
    case 'low': {
      return 'bg-blue-900 text-blue-300 dark:bg-blue-900 dark:text-blue-300';
    }
    case 'very low': {
      return 'bg-gray-900 text-gray-300 dark:bg-gray-900 dark:text-gray-300';
    }
    default: {
      return 'bg-gray-900 text-gray-300 dark:bg-gray-900 dark:text-gray-300';
    }
  }
};
