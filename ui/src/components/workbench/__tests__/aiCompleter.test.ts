/* eslint-disable @typescript-eslint/no-unnecessary-type-assertion */
/* eslint-disable @typescript-eslint/unbound-method */
import type { Ace } from 'ace-builds';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the scriptCompletionApi before importing aiCompleter
vi.mock('../../../services/scriptCompletionApi', () => ({
  getScriptCompletion: vi.fn(),
}));

import { getScriptCompletion } from '../../../services/scriptCompletionApi';
import {
  aiCompleter,
  cancelAiCompletion,
  schedulAiCompletion,
  setPendingCompletion,
  stripDuplicateClosingBrackets,
} from '../aiCompleter';

const mockGetScriptCompletion = vi.mocked(getScriptCompletion);

// Shared test fixtures
const ALERT_LINE = 'alert = input';

// ---------------------------------------------------------------------------
// Helpers to build mock Ace editor
// ---------------------------------------------------------------------------

interface MockEditorOptions {
  cursorRow?: number;
  cursorColumn?: number;
  lines?: string[];
  popupOpen?: boolean;
}

function createMockEditor(opts: MockEditorOptions = {}): Ace.Editor {
  const { cursorRow = 0, cursorColumn = 0, lines = [''], popupOpen = false } = opts;

  return {
    getCursorPosition: () => ({ row: cursorRow, column: cursorColumn }),
    session: {
      getLine: (row: number) => lines[row] ?? '',
      getLines: (start: number, end: number) => lines.slice(start, end + 1),
      getLength: () => lines.length,
    },
    execCommand: vi.fn(),

    completer: popupOpen ? { popup: { isOpen: true } } : undefined,
  } as unknown as Ace.Editor;
}

// ---------------------------------------------------------------------------
// aiCompleter.getCompletions
// ---------------------------------------------------------------------------

describe('aiCompleter.getCompletions', () => {
  beforeEach(() => {
    setPendingCompletion(null);
  });

  it('returns empty array when no pending completion is set', () => {
    return new Promise<void>((resolve) => {
      aiCompleter.getCompletions!(
        {} as Ace.Editor,
        {} as Ace.EditSession,
        {} as Ace.Point,
        '',
        (err, completions) => {
          expect(err).toBeNull();
          expect(completions).toEqual([]);
          resolve();
        }
      );
    });
  });

  it('returns the pending completion when one has been set', () => {
    setPendingCompletion('src_ip = alert["src_ip"] ?? null');

    return new Promise<void>((resolve) => {
      aiCompleter.getCompletions!(
        {} as Ace.Editor,
        {} as Ace.EditSession,
        {} as Ace.Point,
        '',
        (err, completions) => {
          expect(err).toBeNull();
          expect(completions).toHaveLength(1);
          expect(completions![0].value).toBe('src_ip = alert["src_ip"] ?? null');
          expect(completions![0].caption).toBe('src_ip = alert["src_ip"] ?? null');
          expect(completions![0].meta).toBe('✦ AI');
          expect(completions![0].score).toBe(2000);
          resolve();
        }
      );
    });
  });

  it('clears the pending completion after returning it (consumed once)', () => {
    setPendingCompletion('observables = alert.observables ?? []');

    return new Promise<void>((resolve) => {
      // First call returns the completion
      aiCompleter.getCompletions!(
        {} as Ace.Editor,
        {} as Ace.EditSession,
        {} as Ace.Point,
        '',
        (_err1, completions1) => {
          expect(completions1).toHaveLength(1);

          // Second call should return empty (completion was consumed)
          aiCompleter.getCompletions!(
            {} as Ace.Editor,
            {} as Ace.EditSession,
            {} as Ace.Point,
            '',
            (err2, completions2) => {
              expect(err2).toBeNull();
              expect(completions2).toEqual([]);
              resolve();
            }
          );
        }
      );
    });
  });

  it('returns empty array for whitespace-only pending completion', () => {
    setPendingCompletion('   \n  ');

    return new Promise<void>((resolve) => {
      aiCompleter.getCompletions!(
        {} as Ace.Editor,
        {} as Ace.EditSession,
        {} as Ace.Point,
        '',
        (err, completions) => {
          expect(err).toBeNull();
          expect(completions).toEqual([]);
          resolve();
        }
      );
    });
  });
});

// ---------------------------------------------------------------------------
// schedulAiCompletion
// ---------------------------------------------------------------------------

describe('schedulAiCompletion', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setPendingCompletion(null);
    mockGetScriptCompletion.mockReset();
  });

  afterEach(() => {
    cancelAiCompletion();
    vi.useRealTimers();
  });

  it('does not call API when prefix is too short (< 5 non-whitespace chars)', async () => {
    const editor = createMockEditor({
      cursorRow: 0,
      cursorColumn: 4,
      lines: ['hi  '],
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();

    expect(mockGetScriptCompletion).not.toHaveBeenCalled();
  });

  it('does not call API when current line starts with a comment (#)', async () => {
    const editor = createMockEditor({
      cursorRow: 0,
      cursorColumn: 20,
      lines: ['# this is a comment'],
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();

    expect(mockGetScriptCompletion).not.toHaveBeenCalled();
  });

  it('does not call API when indented comment', async () => {
    const editor = createMockEditor({
      cursorRow: 0,
      cursorColumn: 25,
      lines: ['  # indented comment here'],
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();

    expect(mockGetScriptCompletion).not.toHaveBeenCalled();
  });

  it('still calls API even when popup autocomplete is open (both can show simultaneously)', async () => {
    mockGetScriptCompletion.mockResolvedValue(null);

    const editor = createMockEditor({
      cursorRow: 0,
      cursorColumn: 12,
      lines: [ALERT_LINE],
      popupOpen: true,
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();

    // AI completion fires regardless of popup state — popup handles Tab for symbol names,
    // ghost text handles Tab for longer AI completions; they coexist independently.
    expect(mockGetScriptCompletion).toHaveBeenCalled();
  });

  it('detects trigger_kind "newline" when current line is empty', async () => {
    mockGetScriptCompletion.mockResolvedValue(null);

    const editor = createMockEditor({
      cursorRow: 1,
      cursorColumn: 0,
      lines: [ALERT_LINE, ''],
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();

    expect(mockGetScriptCompletion).toHaveBeenCalledWith(
      expect.objectContaining({ trigger_kind: 'newline' })
    );
  });

  it('detects trigger_kind "character" when cursor is mid-line (auto-triggered while typing)', async () => {
    mockGetScriptCompletion.mockResolvedValue(null);

    const editor = createMockEditor({
      cursorRow: 0,
      cursorColumn: 12,
      lines: [ALERT_LINE],
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();

    expect(mockGetScriptCompletion).toHaveBeenCalledWith(
      expect.objectContaining({ trigger_kind: 'character' })
    );
  });

  it('builds prefix from lines above + current line up to cursor', async () => {
    mockGetScriptCompletion.mockResolvedValue(null);

    const editor = createMockEditor({
      cursorRow: 2,
      cursorColumn: 6,
      lines: ['line1', 'line2', 'line3 rest'],
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();

    expect(mockGetScriptCompletion).toHaveBeenCalledWith(
      expect.objectContaining({
        prefix: 'line1\nline2\nline3 ',
      })
    );
  });

  it('builds suffix from rest of current line and lines below', async () => {
    mockGetScriptCompletion.mockResolvedValue(null);

    // cursor at col 5: 'line2|after_cursor'  → suffix starts at char 5
    // 'line2 after_cursor'.substring(5) = ' after_cursor'
    const editor = createMockEditor({
      cursorRow: 1,
      cursorColumn: 5,
      lines: ['line1', 'line2 after_cursor', 'line3'],
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();

    expect(mockGetScriptCompletion).toHaveBeenCalledWith(
      expect.objectContaining({
        suffix: ' after_cursor\nline3',
      })
    );
  });

  it('sets pending completion and triggers startInlineAutocomplete on success', async () => {
    const completionText = 'src_ip = alert["src_ip"] ?? null';
    mockGetScriptCompletion.mockResolvedValue(completionText);

    const editor = createMockEditor({
      cursorRow: 1,
      cursorColumn: 0,
      lines: [ALERT_LINE, ''],
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();
    // Allow the resolved promise to execute
    await Promise.resolve();

    expect(editor.execCommand).toHaveBeenCalledWith('startInlineAutocomplete');

    // Verify pending completion was set (consuming it returns the value)
    return new Promise<void>((resolve) => {
      aiCompleter.getCompletions!(
        {} as Ace.Editor,
        {} as Ace.EditSession,
        {} as Ace.Point,
        '',
        (_err, completions) => {
          expect(completions).toHaveLength(1);
          expect(completions![0].value).toBe(completionText);
          resolve();
        }
      );
    });
  });

  it('does not trigger startInlineAutocomplete when API returns null', async () => {
    mockGetScriptCompletion.mockResolvedValue(null);

    const editor = createMockEditor({
      cursorRow: 1,
      cursorColumn: 0,
      lines: [ALERT_LINE, ''],
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();
    await Promise.resolve();

    expect(editor.execCommand).not.toHaveBeenCalled();
  });

  it('does not trigger startInlineAutocomplete when API returns whitespace-only string', async () => {
    mockGetScriptCompletion.mockResolvedValue('   ');

    const editor = createMockEditor({
      cursorRow: 1,
      cursorColumn: 0,
      lines: [ALERT_LINE, ''],
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();
    await Promise.resolve();

    expect(editor.execCommand).not.toHaveBeenCalled();
  });

  it('does not trigger startInlineAutocomplete when API throws', async () => {
    mockGetScriptCompletion.mockRejectedValue(new Error('Network error'));

    const editor = createMockEditor({
      cursorRow: 1,
      cursorColumn: 0,
      lines: [ALERT_LINE, ''],
    });

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();
    await Promise.resolve();

    expect(editor.execCommand).not.toHaveBeenCalled();
  });

  it('debounces: cancels previous timer when called again before delay', async () => {
    mockGetScriptCompletion.mockResolvedValue('some completion');

    const editor = createMockEditor({
      cursorRow: 0,
      cursorColumn: 12,
      lines: [ALERT_LINE],
    });

    // Call twice quickly
    schedulAiCompletion(editor, 500);
    schedulAiCompletion(editor, 500);

    await vi.runAllTimersAsync();
    await Promise.resolve();

    // API should only be called once (second call cancelled the first timer)
    expect(mockGetScriptCompletion).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// cancelAiCompletion
// ---------------------------------------------------------------------------

describe('cancelAiCompletion', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockGetScriptCompletion.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('cancels pending timer so API is never called', async () => {
    mockGetScriptCompletion.mockResolvedValue('some completion');

    const editor = createMockEditor({
      cursorRow: 0,
      cursorColumn: 12,
      lines: [ALERT_LINE],
    });

    schedulAiCompletion(editor, 500);
    cancelAiCompletion();

    await vi.runAllTimersAsync();
    await Promise.resolve();

    expect(mockGetScriptCompletion).not.toHaveBeenCalled();
  });

  it('is safe to call when no pending timer exists', () => {
    expect(() => cancelAiCompletion()).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// stripDuplicateClosingBrackets
// ---------------------------------------------------------------------------

describe('stripDuplicateClosingBrackets', () => {
  // Set up fake timers + clean state for integration tests within this suite
  beforeEach(() => {
    vi.useFakeTimers();
    setPendingCompletion(null);
    mockGetScriptCompletion.mockReset();
  });

  afterEach(() => {
    cancelAiCompletion();
    vi.useRealTimers();
  });
  // --- Stripping cases ---

  it('strips trailing ] when ] is immediately after cursor', () => {
    // cursor inside [|]  → insert_text "3]" → should become "3"
    expect(stripDuplicateClosingBrackets('3]', ']')).toBe('3');
  });

  it('strips trailing ) when ) is immediately after cursor', () => {
    // cursor inside fn(|)  → insert_text "arg)" → should become "arg"
    expect(stripDuplicateClosingBrackets('arg)', ')')).toBe('arg');
  });

  it('strips multiple trailing brackets matching textAfterCursor', () => {
    // cursor inside [[|]]  → insert_text "x]]" → should become "x"
    expect(stripDuplicateClosingBrackets('x]]', ']]')).toBe('x');
  });

  it('strips mixed trailing brackets matching textAfterCursor', () => {
    // cursor inside fn([|])  → insert_text "b])" → textAfterCursor "])"
    expect(stripDuplicateClosingBrackets('b])', '])')).toBe('b');
  });

  it('strips trailing } when } is immediately after cursor', () => {
    expect(stripDuplicateClosingBrackets('key: val}', '}')).toBe('key: val');
  });

  // --- Non-stripping cases ---

  it('does NOT strip when insert_text brackets are balanced (self-contained pair)', () => {
    // fn(|)  → insert_text "foo(bar)"  — the ) closes foo's own (
    expect(stripDuplicateClosingBrackets('foo(bar)', ')')).toBe('foo(bar)');
  });

  it('does NOT strip when insert_text has no trailing closing bracket', () => {
    // [|]  → insert_text "3"  — no closing bracket to strip
    expect(stripDuplicateClosingBrackets('3', ']')).toBe('3');
  });

  it('does NOT strip when textAfterCursor does not start with the trailing bracket', () => {
    // insert_text "3]" but textAfterCursor is ")" (different bracket)
    expect(stripDuplicateClosingBrackets('3]', ')')).toBe('3]');
  });

  it('does NOT strip when textAfterCursor is empty', () => {
    expect(stripDuplicateClosingBrackets('3]', '')).toBe('3]');
  });

  it('does NOT strip a complete list literal [1, 2, 3]', () => {
    // insert_text is a complete balanced expression
    expect(stripDuplicateClosingBrackets('[1, 2, 3]', ']')).toBe('[1, 2, 3]');
  });

  it('returns insert_text unchanged when it contains no closing brackets', () => {
    expect(stripDuplicateClosingBrackets(ALERT_LINE, ']')).toBe(ALERT_LINE);
  });

  it('returns empty string when insert_text is empty', () => {
    expect(stripDuplicateClosingBrackets('', ']')).toBe('');
  });

  // --- Integration: bracket stripping in schedulAiCompletion ---

  it('strips duplicate closing bracket before setting pending completion', async () => {
    // Simulate cursor inside [|]  → textAfterCursor starts with "]"
    // "result = [" is 10 chars (indices 0-9), so column 10 is inside the brackets
    const editor = createMockEditor({
      cursorRow: 0,
      cursorColumn: 10, // after "result = [", cursor between [ and ]
      lines: ['result = []'],
    });

    // API returns "1, 2, 3]" — trailing ] would duplicate the auto-inserted ]
    mockGetScriptCompletion.mockResolvedValue('1, 2, 3]');

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();
    await Promise.resolve();

    // Should have triggered startInlineAutocomplete
    expect(editor.execCommand).toHaveBeenCalledWith('startInlineAutocomplete');

    // Pending completion should have the ] stripped
    return new Promise<void>((resolve) => {
      aiCompleter.getCompletions!(
        {} as Ace.Editor,
        {} as Ace.EditSession,
        {} as Ace.Point,
        '',
        (_err, completions) => {
          expect(completions).toHaveLength(1);
          expect(completions![0].value).toBe('1, 2, 3');
          resolve();
        }
      );
    });
  });

  it('does not strip when API returns balanced completion (no duplicate)', async () => {
    const editor = createMockEditor({
      cursorRow: 1,
      cursorColumn: 0,
      lines: [ALERT_LINE, ''],
    });

    // API returns a fully balanced expression — nothing should be stripped
    mockGetScriptCompletion.mockResolvedValue('result = [1, 2, 3]');

    schedulAiCompletion(editor, 100);
    await vi.runAllTimersAsync();
    await Promise.resolve();

    return new Promise<void>((resolve) => {
      aiCompleter.getCompletions!(
        {} as Ace.Editor,
        {} as Ace.EditSession,
        {} as Ace.Point,
        '',
        (_err, completions) => {
          expect(completions).toHaveLength(1);
          expect(completions![0].value).toBe('result = [1, 2, 3]');
          resolve();
        }
      );
    });
  });
});
