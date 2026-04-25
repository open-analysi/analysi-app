/**
 * AI Inline Completer for Ace Editor
 *
 * Provides Copilot-style ghost text completions powered by the script completion API.
 * Designed to work alongside cyCompleter: cyCompleter handles symbol/keyword popup
 * completions while this handles multi-token inline completions.
 *
 * Usage:
 *   - Add to the inline completers list (not the popup completers)
 *   - Set `enableInlineAutocompletion: true` on the editor
 *   - Call `triggerAiInlineCompletion(editor)` after a debounce on content change
 */

import type { Ace } from 'ace-builds';

import { getScriptCompletion } from '../../services/scriptCompletionApi';

// ---------------------------------------------------------------------------
// Bracket-skip deduplication
// ---------------------------------------------------------------------------

/**
 * Strips trailing closing brackets from `insertText` that would duplicate
 * auto-inserted closing characters already present in `textAfterCursor`.
 *
 * Ace auto-inserts the matching closing bracket when you type an opener —
 * e.g., typing `[` produces `[|]` with the cursor between. If the AI
 * completion includes the same closing bracket (e.g., `3]`), naively
 * inserting it at the cursor produces `[1,2,3]]` — a duplicate.
 *
 * Supported pairs: `()`, `[]`, `{}`. Angle brackets `<>` are excluded
 * because `>` doubles as a comparison operator in Cy.
 *
 * This function only strips brackets that are UNBALANCED within `insertText`,
 * i.e., they close something opened BEFORE the cursor (not a pair introduced
 * by the completion itself).
 *
 * Examples:
 *   ('3]',       ']')  → '3'        closes auto-inserted ]
 *   ('arg)',     ')')  → 'arg'      closes auto-inserted )
 *   ('b])',      '])') → 'b'        closes auto-inserted ])
 *   ('foo(bar)', ')')  → 'foo(bar)' balanced — ) closes its own (
 *   ('3',        ']')  → '3'        no closing bracket to strip
 */
// Note: <> intentionally excluded — `>` is also a comparison operator in Cy,
// so treating it as a closing bracket would cause false positives.
const BRACKET_OPEN_TO_CLOSE: Record<string, string> = { '(': ')', '[': ']', '{': '}' };
const BRACKET_CLOSING = new Set([')', ']', '}']);

/**
 * Returns the set of positions in `text` where a closing bracket is unbalanced
 * — i.e., it closes something opened before the start of `text`.
 */
function findUnbalancedClosePositions(text: string): Set<number> {
  const stack: string[] = [];
  const unbalanced = new Set<number>();
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch in BRACKET_OPEN_TO_CLOSE) {
      stack.push(BRACKET_OPEN_TO_CLOSE[ch]);
    } else if (BRACKET_CLOSING.has(ch)) {
      if (stack.length > 0 && stack[stack.length - 1] === ch) {
        stack.pop(); // balanced within text
      } else {
        unbalanced.add(i); // closes something before the start of text
      }
    }
  }
  return unbalanced;
}

export function stripDuplicateClosingBrackets(insertText: string, textAfterCursor: string): string {
  const unbalanced = findUnbalancedClosePositions(insertText);

  // Find the rightmost contiguous run of unbalanced closing brackets at the end
  let trailStart = insertText.length;
  for (let i = insertText.length - 1; i >= 0; i--) {
    if (BRACKET_CLOSING.has(insertText[i]) && unbalanced.has(i)) {
      trailStart = i;
    } else {
      break;
    }
  }

  if (trailStart === insertText.length) return insertText; // nothing to strip

  // Strip only when textAfterCursor starts with the same trailing bracket sequence
  const trailingBrackets = insertText.slice(trailStart);
  if (textAfterCursor.startsWith(trailingBrackets)) {
    return insertText.slice(0, trailStart);
  }

  return insertText;
}

/**
 * Pre-fetched completion result.
 * Populated BEFORE startInlineAutocomplete is called so getCompletions
 * can return synchronously (avoiding Ace's race condition where $updatePrefix
 * fires before async callbacks complete).
 */
let _pendingCompletion: string | null = null;

export function setPendingCompletion(value: string | null): void {
  _pendingCompletion = value;
}

/**
 * The Ace completer object for AI inline (ghost text) completions.
 *
 * Must be added to the editor's completers list alongside cyCompleter.
 * Only responds when activateInlineTrigger() has been called, preventing
 * interference with the regular popup autocomplete.
 */
export const aiCompleter: Ace.Completer = {
  id: 'ai',

  getCompletions: (
    _editor: Ace.Editor,
    _session: Ace.EditSession,
    _pos: Ace.Point,
    _prefix: string,
    callback: Ace.CompleterCallback
  ) => {
    // Only return the pre-fetched AI completion (set before startInlineAutocomplete fires)
    const completion = _pendingCompletion;
    _pendingCompletion = null;

    if (!completion || completion.trim().length === 0) {
      console.log('[AI completer] no pending completion');
      callback(null, []);
      return;
    }

    console.log('[AI completer] returning completion:', completion.slice(0, 50));
    // eslint-disable-next-line @typescript-eslint/no-unsafe-argument
    callback(null, [
      {
        caption: completion,
        value: completion,
        meta: '✦ AI',
        score: 2000,
        // skipFilter ensures it always passes Ace's prefix filter
        snippet: undefined,
        skipFilter: true,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any,
    ]);
  },

  getDocTooltip: () => undefined,
};

// ---------------------------------------------------------------------------
// Trigger helper
// ---------------------------------------------------------------------------

let _pendingTrigger: ReturnType<typeof setTimeout> | null = null;

/**
 * Debounced trigger for inline AI completion.
 * Call this on every editor `change` event; it will debounce and then fire
 * `startInlineAutocomplete` which invokes aiCompleter.getCompletions.
 *
 * Only fires when the popup autocomplete is NOT currently open (to avoid
 * interfering with symbol completions while the user is actively selecting).
 */
export function schedulAiCompletion(editor: Ace.Editor, delayMs = 400): void {
  if (_pendingTrigger !== null) {
    clearTimeout(_pendingTrigger);
  }

  _pendingTrigger = setTimeout(() => {
    _pendingTrigger = null;

    // Don't trigger if there's no meaningful prefix to work from
    const pos = editor.getCursorPosition();
    const linesAbove = editor.session.getLines(0, pos.row - 1);
    const currentLine = editor.session.getLine(pos.row).substring(0, pos.column);
    const prefix = [...linesAbove, currentLine].join('\n');

    if (prefix.trim().length < 5) return;

    // Don't trigger inside comments
    if (currentLine.trimStart().startsWith('#')) return;

    // Build suffix (everything after the cursor on the current line to end of file)
    const linesBelow = editor.session.getLines(pos.row, editor.session.getLength() - 1);
    const currentLineAfterCursor = editor.session.getLine(pos.row).substring(pos.column);
    linesBelow[0] = currentLineAfterCursor;
    const suffix = linesBelow.join('\n');

    // Determine trigger kind per backend spec:
    //   'newline'   — cursor at start of an empty-ish line (user pressed Enter)
    //   'character' — auto-trigger while typing (debounced)
    //   'invoked'   — explicit Ctrl+Space (not used here; handled separately if needed)
    const triggerKind = currentLine.trim() === '' ? 'newline' : 'character';

    console.log('[AI] fetching completion, prefix length:', prefix.length, 'trigger:', triggerKind);

    // Pre-fetch the completion BEFORE triggering startInlineAutocomplete.
    // This avoids a race condition where Ace's $updatePrefix fires during
    // an async callback and crashes because this.completions is not set yet.
    getScriptCompletion({ prefix, suffix, trigger_kind: triggerKind })
      .then((completion) => {
        if (!completion || completion.trim().length === 0) {
          console.log('[AI] no completion returned');
          return;
        }
        // Strip trailing closing brackets that would duplicate auto-inserted ones
        // (e.g., typing [ auto-inserts ] — if insert_text ends with ], skip it)
        const adjusted = stripDuplicateClosingBrackets(completion, suffix);
        if (!adjusted || adjusted.trim().length === 0) {
          console.log('[AI] completion empty after bracket deduplication');
          return;
        }
        console.log('[AI] completion ready, triggering inline:', adjusted.slice(0, 50));
        setPendingCompletion(adjusted);
        editor.execCommand('startInlineAutocomplete');
      })
      .catch((err) => {
        console.log('[AI] completion fetch error:', err);
      });
  }, delayMs);
}

/**
 * Cancel any pending AI completion trigger (e.g., when editor unmounts).
 */
export function cancelAiCompletion(): void {
  if (_pendingTrigger !== null) {
    clearTimeout(_pendingTrigger);
    _pendingTrigger = null;
  }
}
