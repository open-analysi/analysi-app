/**
 * OutputRenderer - Displays task execution output
 *
 * Theme: Uses the centralized dark theme from src/styles/theme.ts
 * - Error backgrounds: bg-red-900/10, border-red-800
 * - Component backgrounds: bg-dark-700
 * - Borders: border-gray-600, border-red-700
 * - Text: text-gray-100, text-gray-400, text-red-400
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';

import { diff as computeDiff } from 'jsondiffpatch';
import { format as formatDiffHtml } from 'jsondiffpatch/formatters/html';
import 'jsondiffpatch/formatters/styles/html.css';

/**
 * Parse a string into a JavaScript object for structural diff comparison.
 * Cy 0.38+ returns native Python objects serialized as valid JSON,
 * so this is a straightforward JSON.parse.
 */
const parseToObject = (str: string): unknown => {
  try {
    const parsed: unknown = JSON.parse(str);
    if (typeof parsed === 'object' && parsed !== null) return parsed;
  } catch {
    /* not valid JSON */
  }
  return null;
};

/**
 * Extract displayable text from task output.
 * Cy 0.38+ outputs valid JSON (dict, list, string, number, etc.).
 * Special-cases: extract error messages and text_content fields for readability.
 */
const extractAndProcessText = (output: string): string => {
  if (!output) return '';

  try {
    const parsed: unknown = JSON.parse(output);

    if (typeof parsed === 'object' && parsed !== null) {
      const obj = parsed as Record<string, unknown>;
      // Extract error message for readable display
      if (obj.error && typeof obj.error === 'string') {
        return processEscapedText(obj.error);
      }
      // Extract text_content field if present
      if (obj.text_content) {
        return processEscapedText(obj.text_content);
      }
    }

    // Pretty-print any valid JSON (objects, arrays, strings, numbers, booleans, null)
    return JSON.stringify(parsed, null, 2);
  } catch {
    // Not valid JSON — return as-is
    return output;
  }
};

// Helper function to process escaped text characters
const processEscapedText = (textContent: unknown): string => {
  // Ensure textContent is a string with proper type checking
  let stringContent: string;
  if (typeof textContent === 'string') {
    stringContent = textContent;
  } else if (typeof textContent === 'number' || typeof textContent === 'boolean') {
    stringContent = String(textContent);
  } else {
    stringContent = '';
  }

  // Convert escaped characters to actual characters
  return stringContent
    .replaceAll('\\n', '\n')
    .replaceAll('\\t', '\t')
    .replaceAll('\\r', '\r')
    .replaceAll('\\\\', '\\');
};

// ANSI color code to Tailwind CSS class mapping
const ansiColorMap: Record<number, string> = {
  // Standard colors (foreground)
  30: 'text-gray-900', // Black
  31: 'text-red-500', // Red
  32: 'text-green-500', // Green
  33: 'text-yellow-500', // Yellow
  34: 'text-blue-500', // Blue
  35: 'text-purple-500', // Magenta
  36: 'text-cyan-500', // Cyan
  37: 'text-gray-200', // White
  // Bright colors (foreground)
  90: 'text-gray-500', // Bright Black (Gray)
  91: 'text-red-400', // Bright Red
  92: 'text-green-400', // Bright Green
  93: 'text-yellow-400', // Bright Yellow
  94: 'text-blue-400', // Bright Blue
  95: 'text-purple-400', // Bright Magenta
  96: 'text-cyan-400', // Bright Cyan
  97: 'text-white', // Bright White
};

// Parse ANSI escape codes and return styled React elements
// eslint-disable-next-line sonarjs/cognitive-complexity
const parseAnsiText = (text: string): React.ReactNode[] => {
  const result: React.ReactNode[] = [];
  // Match ANSI escape sequences: ESC[<codes>m
  // ESC can be \x1b (hex), \u001b (unicode), or sometimes the escape char is stripped leaving just [xxm
  // Also handle cases where escape char appears as literal text
  // eslint-disable-next-line no-control-regex, sonarjs/no-control-regex
  const ansiRegex = /\x1b?\[([0-9;]*)m/g;

  let lastIndex = 0;
  let currentClass = '';
  let match: RegExpExecArray | null;
  let keyIndex = 0;

  while ((match = ansiRegex.exec(text)) !== null) {
    // Add text before this escape sequence with current styling
    if (match.index > lastIndex) {
      const segment = text.slice(lastIndex, match.index);
      if (segment) {
        result.push(
          currentClass ? (
            <span key={keyIndex++} className={currentClass}>
              {segment}
            </span>
          ) : (
            <span key={keyIndex++}>{segment}</span>
          )
        );
      }
    }

    // Parse the ANSI code(s)
    const codes = (match[1] || '0').split(';').map(Number);

    for (const code of codes) {
      if (code === 0) {
        // Reset
        currentClass = '';
      } else if (ansiColorMap[code]) {
        currentClass = ansiColorMap[code];
      }
      // Bold (1), underline (4), etc. could be added here
    }

    lastIndex = ansiRegex.lastIndex;
  }

  // Add remaining text after last escape sequence
  if (lastIndex < text.length) {
    const segment = text.slice(lastIndex);
    if (segment) {
      result.push(
        currentClass ? (
          <span key={keyIndex++} className={currentClass}>
            {segment}
          </span>
        ) : (
          <span key={keyIndex++}>{segment}</span>
        )
      );
    }
  }

  // If no ANSI codes were found, return the original text
  if (result.length === 0) {
    return [<span key={0}>{text}</span>];
  }

  return result;
};

/** Dark-theme CSS overrides for jsondiffpatch HTML formatter.
 *  The library defaults use `display: inline-block` on the root delta and
 *  all `pre` elements, which lets them grow wider than their container and
 *  push the entire page layout to the right.  Override to `block` so
 *  content respects the container width. */
const DIFF_DARK_STYLES = `
  .jsondiffpatch-delta { font-size: 0.875rem; color: #d1d5db; display: block; max-width: 100%; overflow-wrap: anywhere; }
  .jsondiffpatch-delta pre { font-size: 0.875rem; display: inline; white-space: pre-wrap; overflow-wrap: anywhere; }
  .jsondiffpatch-delta ul { max-width: 100%; }
  .jsondiffpatch-added .jsondiffpatch-property-name,
  .jsondiffpatch-added .jsondiffpatch-value pre,
  .jsondiffpatch-modified .jsondiffpatch-right-value pre,
  .jsondiffpatch-textdiff-added { background: rgba(22,101,52,0.3); color: #86efac; }
  .jsondiffpatch-deleted .jsondiffpatch-property-name,
  .jsondiffpatch-deleted pre,
  .jsondiffpatch-modified .jsondiffpatch-left-value pre,
  .jsondiffpatch-textdiff-deleted { background: rgba(127,29,29,0.3); color: #fca5a5; text-decoration: line-through; }
  .jsondiffpatch-unchanged { color: #6b7280; }
  .jsondiffpatch-unchanged-showing .jsondiffpatch-unchanged,
  .jsondiffpatch-unchanged-visible .jsondiffpatch-unchanged { max-height: 200px; }
`;

interface OutputRendererProps {
  output: string;
  onCopy?: () => void;
  isCopied?: boolean;
  /** Explicit error status from task execution. When provided, takes precedence over output inspection. */
  isError?: boolean;
  /** Raw input JSON string for diff comparison */
  inputData?: string;
  /** Current execution status — used to render paused state */
  executionStatus?: string;
}

export const OutputRenderer: React.FC<OutputRendererProps> = ({
  output,
  onCopy,
  isCopied,
  isError = false,
  inputData,
  executionStatus,
}) => {
  const [viewMode, setViewMode] = useState<'output' | 'diff'>('output');
  const diffContainerRef = useRef<HTMLDivElement>(null);

  const showDiffToggle = Boolean(inputData?.trim());

  const diffResult = useMemo(() => {
    if (viewMode !== 'diff' || !inputData?.trim()) return undefined;
    // Normalize both sides to objects for structural comparison.
    // This handles Python dict output being compared to JSON input.
    const left = parseToObject(inputData);
    const right = parseToObject(output);
    if (!left || !right) return null; // Can't diff non-objects
    const delta = computeDiff(left, right);
    if (!delta) return { html: '', noDiff: true };
    const html = formatDiffHtml(delta, left) ?? '';
    return { html, noDiff: false };
  }, [viewMode, inputData, output]);

  // Scroll to the first change when switching to diff mode.
  // IMPORTANT: Do NOT use scrollIntoView or offsetTop — they shift the page
  // viewport with jsondiffpatch HTML. Use getBoundingClientRect for reliable
  // relative positioning and only set container.scrollTop.
  useEffect(() => {
    if (viewMode !== 'diff' || !diffContainerRef.current) return;
    const container = diffContainerRef.current;
    const firstChange = container.querySelector(
      '.jsondiffpatch-added, .jsondiffpatch-deleted, .jsondiffpatch-modified'
    );
    if (firstChange) {
      const containerRect = container.getBoundingClientRect();
      const changeRect = firstChange.getBoundingClientRect();
      const relativeTop = changeRect.top - containerRect.top + container.scrollTop;
      container.scrollTop = Math.max(0, relativeTop - container.clientHeight / 2);
    }
  }, [viewMode, diffResult]);

  // HITL paused state: detect from executionStatus or output content
  const isPaused =
    executionStatus === 'paused' ||
    (() => {
      try {
        const parsed = JSON.parse(output) as Record<string, unknown>;
        return parsed?.status === 'paused' && parsed?.reason === 'waiting_for_human_response';
      } catch {
        return false;
      }
    })();

  if (isPaused) {
    let question = '';
    let channel = '';
    try {
      const parsed = JSON.parse(output) as Record<string, unknown>;
      question = (parsed?.question as string) || '';
      channel = (parsed?.channel as string) || '';
    } catch {
      // ignore
    }

    return (
      <div className="w-full h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-4 max-w-md text-center px-6">
          {/* Pulsing indicator */}
          <div className="relative">
            <div className="w-12 h-12 rounded-full bg-amber-500/20 flex items-center justify-center">
              <div className="w-8 h-8 rounded-full bg-amber-500/30 flex items-center justify-center animate-pulse">
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="text-amber-400"
                >
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-amber-400 font-medium text-sm">Waiting for Human Response</p>
            <p className="text-gray-400 text-xs">
              This task is paused and waiting for a response in Slack. It will resume automatically
              once someone responds.
            </p>
          </div>

          {question && (
            <div className="w-full bg-gray-800/50 border border-gray-700 rounded-lg p-3 text-left">
              <p className="text-gray-500 text-xs uppercase tracking-wider mb-1">Question</p>
              <p className="text-gray-200 text-sm">{question}</p>
            </div>
          )}

          {channel && (
            <div className="flex items-center gap-1.5 text-xs text-gray-500">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="text-gray-500"
              >
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              <span>Channel: {channel}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (!output.trim()) {
    return (
      <div className="w-full h-full flex items-center justify-center text-gray-400">
        Output will appear here after running the task
      </div>
    );
  }

  const renderPlain = () => {
    const processedText = extractAndProcessText(output);

    return (
      <pre className="w-full h-full overflow-y-auto overflow-x-hidden text-sm text-gray-100 font-mono whitespace-pre-wrap leading-relaxed wrap-break-word break-all overflow-wrap-anywhere">
        {parseAnsiText(processedText)}
      </pre>
    );
  };

  const renderDiffContent = () => {
    if (diffResult === null) {
      return (
        <div className="text-gray-400 text-sm">
          Diff unavailable — input or output is not valid JSON
        </div>
      );
    }
    if (diffResult) {
      if (diffResult.noDiff) {
        return <div className="text-gray-400 text-sm">No differences found</div>;
      }
      return (
        <>
          <style>{DIFF_DARK_STYLES}</style>
          <div
            ref={diffContainerRef}
            className="w-full h-full min-w-0 overflow-y-auto overflow-x-hidden text-sm font-mono whitespace-pre-wrap leading-relaxed jsondiffpatch-unchanged-showing"
            dangerouslySetInnerHTML={{ __html: diffResult.html }}
          />
        </>
      );
    }
    return null;
  };

  return (
    <div
      className={`w-full h-full min-w-0 flex flex-col ${isError ? 'bg-red-900/10 rounded-sm border border-red-800 p-3' : ''}`}
    >
      {/* Header: error indicator, diff toggle, copy button */}
      {(isError || onCopy || showDiffToggle) && (
        <div
          className={`flex items-center justify-between mb-2 pb-2 border-b shrink-0 ${isError ? 'border-red-700' : 'border-gray-600'}`}
        >
          <div className="flex items-center gap-2">
            {isError && (
              <span className="text-xs font-semibold text-red-400 bg-red-900/30 px-2 py-0.5 rounded-sm">
                ERROR
              </span>
            )}
            {showDiffToggle && (
              <div className="flex rounded-sm border border-gray-600 overflow-hidden">
                <button
                  onClick={() => setViewMode('output')}
                  className={`text-xs px-2 py-0.5 ${viewMode === 'output' ? 'bg-primary text-white' : 'bg-dark-700 text-gray-400 hover:text-gray-200'}`}
                >
                  Output
                </button>
                <button
                  onClick={() => setViewMode('diff')}
                  className={`text-xs px-2 py-0.5 ${viewMode === 'diff' ? 'bg-primary text-white' : 'bg-dark-700 text-gray-400 hover:text-gray-200'}`}
                >
                  Diff
                </button>
              </div>
            )}
          </div>
          {onCopy && (
            <button
              onClick={onCopy}
              className="text-xs px-2 py-1 border border-gray-600 rounded-sm hover:bg-gray-600 bg-dark-700 text-gray-100"
              title="Copy output"
            >
              {isCopied ? '✓ Copied' : 'Copy'}
            </button>
          )}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 min-h-0 min-w-0 overflow-hidden">
        {viewMode === 'diff' && showDiffToggle ? renderDiffContent() : renderPlain()}
      </div>
    </div>
  );
};
