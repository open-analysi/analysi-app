/**
 * Centralized Theme Configuration
 *
 * This file contains all theme-related constants to ensure consistency across the application.
 *
 * ## How to Use This Theme System
 *
 * ### For React Components (Tailwind CSS)
 * Components should use the Tailwind classes directly (bg-dark-900, text-white, etc.).
 * The actual color values are centralized in tailwind.config.js, so changing a color
 * there will automatically update all components using that class.
 *
 * Example:
 * ```tsx
 * <div className="bg-dark-900 border border-gray-700">
 *   <h1 className="text-white">Title</h1>
 * </div>
 * ```
 *
 * Document your component's theme usage with a header comment:
 * ```tsx
 * /**
 *  * MyComponent
 *  *
 *  * Theme: Uses the centralized dark theme from src/styles/theme.ts
 *  * - Page background: bg-dark-900
 *  * - Panel backgrounds: bg-dark-800
 *  * ...
 *  *\/
 * ```
 *
 * ### When to Import from theme.ts
 * Only import from this file when you need:
 * 1. **Actual hex color values** (for canvas, charts, or non-Tailwind usage)
 * 2. **Pre-configured className combinations** (for complex repeated patterns)
 * 3. **Component-specific theme configs** (structured theme data)
 *
 * Example - Using hex values for canvas:
 * ```tsx
 * import { colors } from '@/styles/theme';
 * ctx.fillStyle = colors.background.darkest;
 * ```
 *
 * Example - Using pre-configured classes:
 * ```tsx
 * import { classNames } from '@/styles/theme';
 * <input className={classNames.input} />
 * ```
 *
 * ### Changing the Theme
 * To change colors across the entire app:
 * 1. Update color values in tailwind.config.js (e.g., dark-900: '#121212' → '#0A0A0A')
 * 2. Update corresponding hex values in this file's `colors` object
 * 3. All components using those Tailwind classes will automatically update
 *
 * ## Theme Structure
 * - `colors`: Hex color values for JavaScript usage
 * - `components`: Component-specific theme configurations
 * - `classNames`: Pre-configured Tailwind class name combinations
 * - `cn`: Utility function to combine class names
 */

/**
 * Dark color palette matching the Integrations page design
 * These match the Tailwind config dark-* colors
 */
export const colors = {
  // Background colors (darkest to lightest)
  background: {
    darkest: '#121212', // bg-dark-900 - Main app background
    darker: '#1E1E1E', // bg-dark-800 - Panel backgrounds
    dark: '#2D2D2D', // bg-dark-700 - Component backgrounds
    medium: '#3D3D3D', // bg-dark-600 - Hover states, inputs
  },

  // Border colors
  border: {
    default: '#374151', // border-gray-700 - Main borders
    light: '#4B5563', // border-gray-600 - Lighter borders
  },

  // Text colors
  text: {
    primary: '#FFFFFF', // text-white - Main headings
    secondary: '#E5E7EB', // text-gray-100 - Body text
    tertiary: '#D1D5DB', // text-gray-200 - Secondary text
    muted: '#9CA3AF', // text-gray-400 - Muted text
    disabled: '#6B7280', // text-gray-500 - Disabled text
  },

  // Accent colors
  accent: {
    primary: '#FF1493', // primary - Pink accent color
    blue: '#3B82F6', // blue-500 - Hover states for resize handles
    green: '#10B981', // green-600/700 - Success/Run buttons
  },

  // Status colors
  status: {
    success: {
      background: 'rgba(16, 185, 129, 0.2)', // bg-green-500/20
      text: '#34D399', // text-green-400
    },
    error: {
      background: 'rgba(239, 68, 68, 0.2)', // bg-red-500/20
      text: '#F87171', // text-red-400
      border: '#991B1B', // border-red-800
    },
    warning: {
      background: 'rgba(245, 158, 11, 0.2)', // bg-yellow-500/20
      text: '#FBBF24', // text-yellow-400
    },
    info: {
      background: 'rgba(59, 130, 246, 0.2)', // bg-blue-500/20
      text: '#60A5FA', // text-blue-400
    },
  },
} as const;

/**
 * Component-specific theme configurations
 */
export const components = {
  // Panel/Container backgrounds
  panel: {
    background: colors.background.darker,
    border: colors.border.default,
  },

  // Header/Section headers
  header: {
    background: colors.background.darker,
    border: colors.border.default,
    text: colors.text.primary,
  },

  // Input fields
  input: {
    background: colors.background.dark,
    border: colors.border.light,
    text: colors.text.secondary,
    placeholder: colors.text.disabled,
    focus: {
      ring: colors.accent.primary,
    },
  },

  // Buttons
  button: {
    primary: {
      background: colors.accent.green,
      text: colors.text.primary,
      hover: '#047857', // green-700
    },
    secondary: {
      background: colors.background.dark,
      text: colors.text.muted,
      hover: colors.text.primary,
    },
  },

  // Resize handles
  resizeHandle: {
    default: colors.border.default,
    hover: colors.accent.blue,
  },
} as const;

/**
 * Tailwind CSS class names for common patterns
 * Use these instead of hardcoding className strings
 */
export const classNames = {
  // Page backgrounds
  pageBackground: 'bg-dark-900',

  // Panel backgrounds
  panelBackground: 'bg-dark-800',
  panelBorder: 'border-gray-700',

  // Component backgrounds
  componentBackground: 'bg-dark-700',
  componentBorder: 'border-gray-600',

  // Text
  textPrimary: 'text-white',
  textSecondary: 'text-gray-100',
  textTertiary: 'text-gray-200',
  textMuted: 'text-gray-400',

  // Borders
  borderDefault: 'border-gray-700',
  borderLight: 'border-gray-600',

  // Buttons
  buttonPrimary: 'bg-green-600 text-white hover:bg-green-700',
  buttonSecondary: 'bg-dark-700 text-gray-400 hover:text-white hover:bg-dark-600',

  // Inputs
  input:
    'bg-dark-700 border border-gray-600 text-gray-100 placeholder-gray-500 focus:ring-2 focus:ring-primary focus:border-transparent',

  // Resize handles
  resizeHandleHorizontal: 'w-1 bg-gray-700 hover:bg-blue-500 transition-colors cursor-col-resize',
  resizeHandleVertical: 'h-1 bg-gray-700 hover:bg-blue-500 transition-colors cursor-row-resize',
} as const;

/**
 * Helper function to combine class names
 */
export const cn = (...classes: (string | undefined | false)[]): string => {
  return classes.filter(Boolean).join(' ');
};
