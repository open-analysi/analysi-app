/**
 * Component Styles
 *
 * Theme: Uses the centralized dark theme from src/styles/theme.ts
 * Design: Option A - Subtle Table Container
 * - Page background: bg-dark-900
 * - Card/panel backgrounds: bg-dark-800 with subtle border
 * - Table headers: bg-dark-700
 * - Table rows: bg-dark-900 (blend with page, subtle dividers)
 * - Hover state: bg-dark-700 (strong highlight)
 * - Borders: border-gray-700/30, border-gray-700/50
 * - Text: text-white, text-gray-100, text-gray-400
 */
export const componentStyles = {
  // Container styles
  card: 'bg-dark-800 shadow-sm rounded-lg p-6 border border-gray-700/30',

  // Table styles
  table: 'min-w-full divide-y divide-gray-700 table-fixed',
  tableHeader: 'bg-dark-700',
  tableBody: 'bg-dark-900 divide-y divide-gray-700/50',
  tableHeaderCell:
    'px-1 md:px-2 py-1.5 md:py-2 text-left text-xs font-medium text-gray-400 uppercase tracking-wider',
  tableCell: 'px-1 md:px-2 py-2 md:py-2.5 text-xs md:text-sm text-gray-100 wrap-break-word',
  tableRow: 'hover:bg-dark-700 cursor-pointer transition-colors',

  /**
   * Button Styles - Color Usage Guidelines
   *
   * PRIMARY (Pink #FF3B81):
   * - Use for: Primary actions, form submissions, creating/saving data
   * - Examples: "Save", "Submit", "Create Task", "Add Workflow"
   * - Class: bg-primary or bg-[#FF3B81]
   *
   * SUCCESS (Green bg-green-600):
   * - Use for: Execute/Run actions, confirmation actions
   * - Examples: "Execute Workflow", "Run Task", "Start Process"
   * - Inline example: className="bg-green-600 hover:bg-green-700 text-white"
   *
   * SECONDARY (Gray dark-700):
   * - Use for: Cancel, back, secondary navigation
   * - Examples: "Cancel", "Close", "Back"
   * - Inline example: className="bg-dark-700 hover:bg-dark-600 text-gray-300"
   *
   * DANGER (Red bg-red-600):
   * - Use for: Destructive actions, deletions
   * - Examples: "Delete", "Remove", "Terminate"
   * - Inline example: className="bg-red-600 hover:bg-red-700 text-white"
   */
  primaryButton:
    'inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-[#FF3B81] hover:bg-[#FF1B6B]',

  /**
   * Badge Styles - Standardized responsive sizing
   *
   * BADGE (rounded-full):
   * - Use for: Status indicators, severity levels, small labels
   * - Responsive sizing: px-1.5 md:px-2 py-0.5 md:py-1
   * - Font size: text-xs md:text-sm
   * - Examples: StatusBadge, severity badges, disposition badges
   *
   * BADGE PILL (rounded-full, slightly larger):
   * - Use for: Tags, categories, larger labels
   * - Sizing: px-2 md:px-2.5 py-0.5
   * - Font size: text-xs
   * - Examples: Category tags, filter chips
   */
  badge:
    'inline-flex items-center px-1.5 md:px-2 py-0.5 md:py-1 rounded-full text-xs md:text-sm font-medium',
  badgePill: 'inline-flex items-center px-2 md:px-2.5 py-0.5 rounded-full text-xs font-medium',

  // Page background
  pageBackground: 'flex flex-col h-full bg-dark-900',
};
