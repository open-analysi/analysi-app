/**
 * Utility functions and type definitions for the Workbench component.
 * Extracted from WorkbenchModern.tsx to reduce file size and improve testability.
 */

// ─── Type Definitions ────────────────────────────────────────────────

/** Constant key used for ad-hoc draft persistence */
export const ADHOC_DRAFT_KEY = '__adhoc__' as const;

/** Default script content for new/empty editor */
export const DEFAULT_SCRIPT = 'return "Hello World"' as const;

/** Error location extracted from Cy execution error messages */
export interface ErrorLocation {
  line: number;
  column: number;
  message: string;
}

/** Shape of a data sample attached to a Task */
export interface DataSample {
  name?: string;
  description?: string;
  input?: unknown;
  expected_output?: unknown;
}

/** Response from getTaskRuns / getTaskRunHistory */
export interface TaskRunsResponse {
  task_runs: Array<{
    id: string;
    task_name?: string;
    task_id?: string;
    status: string;
    started_at: string;
    created_at?: string;
    updated_at?: string;
  }>;
}

/** Response from getTaskRunDetails */
export interface TaskRunDetailsResponse {
  output_type: string | null;
  output_location: string;
  input_type?: string | null;
  input_location?: string | null;
  status?: string;
  task_id?: string | null;
}

/** Ace language_tools module */
export interface AceLangTools {
  setCompleters: (completers: unknown[]) => void;
}

/** Ace Range constructor */
export interface AceRangeConstructor {
  new (startRow: number, startColumn: number, endRow: number, endColumn: number): unknown;
}

/** Ace range module */
export interface AceRangeModule {
  Range: AceRangeConstructor;
}

/** Ref stored on editor for AI autocomplete toggle */
export interface AiEnabledRef {
  current: boolean;
}

/** Extended IAceEditor type with __aiEnabledRef property */
export interface AceEditorWithAiRef {
  __aiEnabledRef?: AiEnabledRef;
}

// Re-export types already defined in WorkbenchModern.tsx so they stay in one place
export interface IntegrationTool {
  tool_id: string;
  name: string;
  description?: string;
  params_schema?: { type: string; properties?: Record<string, unknown>; required?: string[] };
}

export interface IntegrationType {
  integration_type: string;
  display_name?: string;
  description?: string;
  tools?: IntegrationTool[];
}

export interface ToolSummaryInternal {
  fqn: string;
  name: string;
  description?: string;
  integration_id: string;
  params_schema?: { type: string; properties?: Record<string, unknown>; required?: string[] };
}

export interface TaskRun {
  created_at?: string;
  updated_at?: string;
}

// ─── Pure Functions ──────────────────────────────────────────────────

/**
 * Parse error location from Cy execution output.
 *
 * Backend Error Format (confirmed via testing):
 * - Compilation errors: "Line X, Col Y: <description>"
 * - Runtime errors: "Line X, Column Y: <description>"
 *
 * Examples:
 * - "Line 2, Col 1: Unexpected token Token('$END', '') at line 2, column 1..."
 * - "Line 2, Column 10: Tool 'app::nonexistent_integration::fake_action' not found"
 *
 * @param output - The task execution output string (may be JSON or plain text)
 * @returns ErrorLocation object if error location found, null otherwise
 */
export const parseErrorLocation = (output: string): ErrorLocation | null => {
  if (!output) return null;

  // Try to extract error message from JSON structure first
  let errorText = output;
  try {
    const parsed: Record<string, unknown> = JSON.parse(output) as Record<string, unknown>;
    if (parsed.error && typeof parsed.error === 'string') {
      errorText = parsed.error;
    }
  } catch {
    // Not JSON or parsing failed, use raw output
  }

  // Single pattern that handles both "Col" and "Column" (case-insensitive)
  const pattern = /Line\s+(\d+),\s+Col(?:umn)?\s+(\d+):\s*(.+)/i;
  const match = pattern.exec(errorText);
  if (match) {
    return {
      line: parseInt(match[1], 10),
      column: parseInt(match[2], 10),
      message: match[3].trim(),
    };
  }

  return null;
};

/**
 * Generate a versioned name for Save As.
 * E.g., "My Task" -> "My Task v2", "My Task v2" -> "My Task v3"
 */
export const generateVersionedName = (originalName: string): string => {
  const versionRegex = / v(\d+)$/;
  const match = versionRegex.exec(originalName);
  if (match) {
    const baseName = originalName.slice(0, match.index);
    const currentVersion = parseInt(match[1], 10);
    return `${baseName} v${currentVersion + 1}`;
  }
  return `${originalName} v2`;
};

/**
 * Get Tailwind CSS classes for a tool badge based on its namespace.
 * Extracted to eliminate nested ternary lint errors.
 */
export const getToolNamespaceClasses = (namespace: string): string => {
  if (namespace === 'app') {
    return 'bg-blue-900/50 text-blue-300 hover:bg-blue-900/70';
  }
  if (namespace === 'native') {
    return 'bg-purple-900/50 text-purple-300 hover:bg-purple-900/70';
  }
  return 'bg-gray-700 text-gray-300 hover:bg-gray-600';
};

/**
 * Get Tailwind CSS classes for a task run status badge.
 */
export const getStatusClasses = (status: string): string => {
  if (status === 'completed') {
    return 'text-green-400';
  }
  if (status === 'failed') {
    return 'text-red-400';
  }
  return 'text-gray-400';
};

/**
 * Parse input from a task run for loading into the editor.
 * Handles inline JSON input by pretty-printing objects and passing strings through.
 */
export const parseTaskRunInput = (
  inputType?: string | null,
  inputLocation?: string | null
): string => {
  if (inputType !== 'inline' || !inputLocation) return '';
  try {
    const parsed: unknown = JSON.parse(inputLocation);
    return typeof parsed === 'string' ? parsed : JSON.stringify(parsed, null, 2);
  } catch {
    return inputLocation;
  }
};

/**
 * Parse execution output into a display-ready object.
 * Extracted from the onComplete handler to reduce cognitive complexity.
 */
export const parseExecutionOutput = (
  details: TaskRunDetailsResponse
): { output: unknown; error?: boolean } => {
  try {
    if (details.output_type === 'inline') {
      return { output: JSON.parse(details.output_location) as unknown };
    }
    if (details.output_type === null) {
      return { output: { message: 'No output captured' } };
    }
    return { output: { error: 'S3 storage not yet supported in UI' } };
  } catch {
    return {
      output: {
        error: 'Failed to parse output',
        raw_output: details.output_location,
      },
    };
  }
};
