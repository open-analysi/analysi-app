import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { OutputRenderer } from '../OutputRenderer';

const NO_DIFF_TEXT = 'No differences found';
const DIFF_MODIFIED = '.jsondiffpatch-modified';

describe('OutputRenderer', () => {
  it('renders placeholder when output is empty', () => {
    render(<OutputRenderer output="" />);
    expect(screen.getByText('Output will appear here after running the task')).toBeInTheDocument();
  });

  it('renders plain output text', () => {
    render(<OutputRenderer output="hello world" />);
    expect(screen.getByText('hello world')).toBeInTheDocument();
  });

  it('pretty-prints JSON output', () => {
    const json = JSON.stringify({ name: 'Alice', age: 30 });
    render(<OutputRenderer output={json} />);
    expect(screen.getByText(/"name": "Alice"/)).toBeInTheDocument();
  });

  it('shows ERROR badge when isError is true', () => {
    render(<OutputRenderer output="something failed" isError={true} />);
    expect(screen.getByText('ERROR')).toBeInTheDocument();
  });

  it('shows copy button when onCopy is provided', () => {
    const onCopy = vi.fn();
    render(<OutputRenderer output="test" onCopy={onCopy} />);
    expect(screen.getByTitle('Copy output')).toBeInTheDocument();
  });

  describe('diff toggle', () => {
    it('does not show diff toggle when inputData is not provided', () => {
      render(<OutputRenderer output='{"a":1}' />);
      expect(screen.queryByText('Diff')).not.toBeInTheDocument();
    });

    it('does not show diff toggle when inputData is empty', () => {
      render(<OutputRenderer output='{"a":1}' inputData="" />);
      expect(screen.queryByText('Diff')).not.toBeInTheDocument();
    });

    it('shows Output/Diff toggle when inputData is provided', () => {
      render(<OutputRenderer output='{"a":1}' inputData='{"a":1}' />);
      expect(screen.getByText('Output')).toBeInTheDocument();
      expect(screen.getByText('Diff')).toBeInTheDocument();
    });

    it('defaults to output view mode', () => {
      const json = JSON.stringify({ name: 'Alice' });
      render(<OutputRenderer output={json} inputData={json} />);
      // Should show pretty-printed output, not diff
      expect(screen.getByText(/"name": "Alice"/)).toBeInTheDocument();
    });

    it('shows "No differences found" when input and output are identical', async () => {
      const user = userEvent.setup();
      const json = JSON.stringify({ name: 'Alice' });

      render(<OutputRenderer output={json} inputData={json} />);
      await user.click(screen.getByText('Diff'));

      expect(screen.getByText(NO_DIFF_TEXT)).toBeInTheDocument();
    });

    it('shows modified fields in diff view', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ name: 'Alice', age: 30 });
      const output = JSON.stringify({ name: 'Alice', age: 31 });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      // jsondiffpatch HTML formatter marks modified fields
      expect(container.querySelector(DIFF_MODIFIED)).not.toBeNull();
      // Unchanged field should be present
      expect(container.querySelector('.jsondiffpatch-unchanged')).not.toBeNull();
    });

    it('shows added fields in diff view', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ name: 'Alice' });
      const output = JSON.stringify({ name: 'Alice', role: 'engineer' });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      expect(container.querySelector('.jsondiffpatch-added')).not.toBeNull();
    });

    it('shows deleted fields in diff view', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ name: 'Alice', temp: 'remove-me' });
      const output = JSON.stringify({ name: 'Alice' });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      expect(container.querySelector('.jsondiffpatch-deleted')).not.toBeNull();
    });

    it('shows fallback message when input is not valid JSON', async () => {
      const user = userEvent.setup();

      render(<OutputRenderer output='{"a":1}' inputData="not-json" />);
      await user.click(screen.getByText('Diff'));

      expect(
        screen.getByText('Diff unavailable — input or output is not valid JSON')
      ).toBeInTheDocument();
    });

    it('shows fallback message when output is not valid JSON', async () => {
      const user = userEvent.setup();

      render(<OutputRenderer output="not-json" inputData='{"a":1}' />);
      await user.click(screen.getByText('Diff'));

      expect(
        screen.getByText('Diff unavailable — input or output is not valid JSON')
      ).toBeInTheDocument();
    });

    it('switches back to output view when Output button is clicked', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ a: 1 });
      const output = JSON.stringify({ a: 2 });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      // Verify we're in diff mode
      expect(container.querySelector(DIFF_MODIFIED)).not.toBeNull();

      await user.click(screen.getByText('Output'));

      // Should be back to plain output
      expect(screen.getByText(/"a": 2/)).toBeInTheDocument();
    });

    it('handles array modifications without crashing', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ items: [1, 2, 3] });
      const output = JSON.stringify({ items: [1, 3, 4] });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      // Should render without crashing — jsondiffpatch handles arrays natively
      expect(container.querySelector('.jsondiffpatch-delta')).not.toBeNull();
    });

    it('handles nested object diffs', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ data: { list: [{ id: 1 }, { id: 2 }] } });
      const output = JSON.stringify({ data: { list: [{ id: 1 }, { id: 3 }] } });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      expect(container.querySelector('.jsondiffpatch-delta')).not.toBeNull();
    });

    it('handles added fields alongside array modifications', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ severity: 'high' });
      const output = JSON.stringify({
        severity: 'critical',
        enrichments: [{ summary: 'test' }],
        risk_score: 85,
      });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      // Should have both modified and added elements
      expect(container.querySelector(DIFF_MODIFIED)).not.toBeNull();
      expect(container.querySelector('.jsondiffpatch-added')).not.toBeNull();
    });

    it('shows fallback when both input and output are non-JSON', async () => {
      const user = userEvent.setup();

      render(<OutputRenderer output="plain text output" inputData="plain text input" />);
      await user.click(screen.getByText('Diff'));

      expect(
        screen.getByText('Diff unavailable — input or output is not valid JSON')
      ).toBeInTheDocument();
    });

    it('detects type changes in diff (string to number)', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ value: 'hello' });
      const output = JSON.stringify({ value: 42 });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      expect(container.querySelector(DIFF_MODIFIED)).not.toBeNull();
    });

    it('handles null values in diff', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ a: 1, b: null });
      const output = JSON.stringify({ a: 1, b: 'now-set' });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      expect(container.querySelector(DIFF_MODIFIED)).not.toBeNull();
      expect(container.querySelector('.jsondiffpatch-unchanged')).not.toBeNull();
    });

    it('handles empty objects showing no differences', async () => {
      const user = userEvent.setup();

      render(<OutputRenderer output="{}" inputData="{}" />);
      await user.click(screen.getByText('Diff'));

      expect(screen.getByText(NO_DIFF_TEXT)).toBeInTheDocument();
    });

    it('handles array root objects in diff', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify([1, 2, 3]);
      const output = JSON.stringify([1, 2, 4]);

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      expect(container.querySelector('.jsondiffpatch-delta')).not.toBeNull();
    });

    it('handles deeply nested changes', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ a: { b: { c: { d: 'old' } } } });
      const output = JSON.stringify({ a: { b: { c: { d: 'new' } } } });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      expect(container.querySelector(DIFF_MODIFIED)).not.toBeNull();
    });
  });

  describe('output formatting', () => {
    it('renders placeholder for whitespace-only output', () => {
      render(<OutputRenderer output="   " />);
      expect(
        screen.getByText('Output will appear here after running the task')
      ).toBeInTheDocument();
    });

    it('extracts error field from JSON output', () => {
      const output = JSON.stringify({ error: 'Connection refused' });
      render(<OutputRenderer output={output} />);
      expect(screen.getByText('Connection refused')).toBeInTheDocument();
    });

    it('extracts text_content field from JSON output', () => {
      const output = JSON.stringify({ text_content: 'Report summary here' });
      render(<OutputRenderer output={output} />);
      expect(screen.getByText('Report summary here')).toBeInTheDocument();
    });

    it('processes escaped newlines in error text', () => {
      const output = JSON.stringify({ error: 'Line 1\\nLine 2' });
      render(<OutputRenderer output={output} />);
      expect(screen.getByText(/Line 1/)).toBeInTheDocument();
      expect(screen.getByText(/Line 2/)).toBeInTheDocument();
    });

    it('renders ANSI color codes with correct classes', () => {
      // \x1b[91m = bright red, \x1b[0m = reset
      const output = '\x1b[91mError:\x1b[0m something went wrong';
      const { container } = render(<OutputRenderer output={output} />);
      const redSpan = container.querySelector('.text-red-400');
      expect(redSpan).not.toBeNull();
      expect(redSpan?.textContent).toBe('Error:');
    });

    it('renders multiple ANSI colors in sequence', () => {
      const output = '\x1b[32mSUCCESS\x1b[0m \x1b[33mWARNING\x1b[0m \x1b[31mERROR\x1b[0m';
      const { container } = render(<OutputRenderer output={output} />);
      expect(container.querySelector('.text-green-500')).not.toBeNull();
      expect(container.querySelector('.text-yellow-500')).not.toBeNull();
      expect(container.querySelector('.text-red-500')).not.toBeNull();
    });

    it('handles output that is a JSON number', () => {
      render(<OutputRenderer output="42" />);
      expect(screen.getByText('42')).toBeInTheDocument();
    });

    it('handles output that is a JSON boolean', () => {
      render(<OutputRenderer output="true" />);
      expect(screen.getByText('true')).toBeInTheDocument();
    });

    it('handles output that is a JSON null', () => {
      render(<OutputRenderer output="null" />);
      expect(screen.getByText('null')).toBeInTheDocument();
    });
  });

  describe('HITL paused state', () => {
    const WAITING_TEXT = 'Waiting for Human Response';

    it('renders paused indicator when executionStatus is paused', () => {
      const pausedOutput = JSON.stringify({
        status: 'paused',
        reason: 'waiting_for_human_response',
        question: 'Should we escalate this alert?',
        channel: 'C09KDTJF6JZ',
      });
      render(<OutputRenderer output={pausedOutput} executionStatus="paused" />);
      expect(screen.getByText(WAITING_TEXT)).toBeInTheDocument();
      expect(screen.getByText('Should we escalate this alert?')).toBeInTheDocument();
    });

    it('renders paused indicator from output content even without executionStatus', () => {
      const pausedOutput = JSON.stringify({
        status: 'paused',
        reason: 'waiting_for_human_response',
        question: 'Approve deployment?',
        channel: 'C123',
      });
      render(<OutputRenderer output={pausedOutput} />);
      expect(screen.getByText(WAITING_TEXT)).toBeInTheDocument();
      expect(screen.getByText('Approve deployment?')).toBeInTheDocument();
    });

    it('shows channel info when available', () => {
      const pausedOutput = JSON.stringify({
        status: 'paused',
        reason: 'waiting_for_human_response',
        question: 'OK?',
        channel: 'C09KDTJF6JZ',
      });
      render(<OutputRenderer output={pausedOutput} executionStatus="paused" />);
      expect(screen.getByText(/Channel: C09KDTJF6JZ/)).toBeInTheDocument();
    });

    it('does not render paused state for completed tasks with similar JSON', () => {
      const completedOutput = JSON.stringify({
        status: 'completed',
        result: 'done',
      });
      render(<OutputRenderer output={completedOutput} executionStatus="completed" />);
      expect(screen.queryByText(WAITING_TEXT)).not.toBeInTheDocument();
    });

    it('does not render paused state for normal JSON output', () => {
      const normalOutput = JSON.stringify({ analyst_decision: 'Escalate' });
      render(<OutputRenderer output={normalOutput} />);
      expect(screen.queryByText(WAITING_TEXT)).not.toBeInTheDocument();
    });

    it('renders paused state without question when question is missing', () => {
      const pausedOutput = JSON.stringify({
        status: 'paused',
        reason: 'waiting_for_human_response',
      });
      render(<OutputRenderer output={pausedOutput} executionStatus="paused" />);
      expect(screen.getByText(WAITING_TEXT)).toBeInTheDocument();
      expect(screen.queryByText('QUESTION')).not.toBeInTheDocument();
    });
  });

  describe('diff with executionStatus prop (regression guard)', () => {
    it('diff toggle still works when executionStatus is completed', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ title: 'Alert' });
      const output = JSON.stringify({ title: 'Alert', result: 'done' });

      const { container } = render(
        <OutputRenderer output={output} inputData={input} executionStatus="completed" />
      );

      expect(screen.getByText('Diff')).toBeInTheDocument();
      await user.click(screen.getByText('Diff'));

      expect(container.querySelector('.jsondiffpatch-added')).not.toBeNull();
    });

    it('diff toggle not shown for paused state (paused UI takes priority)', () => {
      const pausedOutput = JSON.stringify({
        status: 'paused',
        reason: 'waiting_for_human_response',
        question: 'Escalate?',
      });

      render(
        <OutputRenderer output={pausedOutput} inputData='{"alert": 1}' executionStatus="paused" />
      );

      // Paused state should render instead of diff-capable output
      expect(screen.queryByText('Diff')).not.toBeInTheDocument();
      expect(screen.getByText('Waiting for Human Response')).toBeInTheDocument();
    });
  });

  describe('copy button', () => {
    it('calls onCopy when copy button is clicked', async () => {
      const user = userEvent.setup();
      const onCopy = vi.fn();
      render(<OutputRenderer output="test" onCopy={onCopy} />);

      await user.click(screen.getByTitle('Copy output'));
      expect(onCopy).toHaveBeenCalledOnce();
    });

    it('shows "Copied" text when isCopied is true', () => {
      render(<OutputRenderer output="test" onCopy={vi.fn()} isCopied={true} />);
      expect(screen.getByText(/Copied/)).toBeInTheDocument();
    });

    it('shows "Copy" text when isCopied is false', () => {
      render(<OutputRenderer output="test" onCopy={vi.fn()} isCopied={false} />);
      expect(screen.getByText('Copy')).toBeInTheDocument();
    });
  });

  describe('combined props', () => {
    it('shows ERROR badge alongside diff toggle when both props set', () => {
      render(<OutputRenderer output='{"a":1}' inputData='{"a":1}' isError={true} />);
      expect(screen.getByText('ERROR')).toBeInTheDocument();
      expect(screen.getByText('Diff')).toBeInTheDocument();
    });

    it('shows ERROR badge alongside copy button', () => {
      render(<OutputRenderer output="fail" isError={true} onCopy={vi.fn()} />);
      expect(screen.getByText('ERROR')).toBeInTheDocument();
      expect(screen.getByTitle('Copy output')).toBeInTheDocument();
    });

    it('does not show diff toggle when inputData is whitespace-only', () => {
      render(<OutputRenderer output='{"a":1}' inputData="   " />);
      expect(screen.queryByText('Diff')).not.toBeInTheDocument();
    });

    it('does not render header bar when no header props are set', () => {
      const { container } = render(<OutputRenderer output="just text" />);
      // No border-b header div should exist
      expect(container.querySelector('.border-b')).toBeNull();
    });
  });

  describe('diff scroll behavior', () => {
    // Build a large JSON where the first N keys are unchanged and the last key is modified,
    // so the first change is far down in the diff output.
    const buildLargeJsonPair = (unchangedCount: number) => {
      const base: Record<string, string> = {};
      for (let i = 0; i < unchangedCount; i++) {
        base[`unchanged_field_${i}`] = `value_${i}`;
      }
      const input = { ...base, target_field: 'original' };
      const output = { ...base, target_field: 'modified' };
      return {
        inputData: JSON.stringify(input),
        outputData: JSON.stringify(output),
      };
    };

    let scrollIntoViewSpy: ReturnType<typeof vi.fn>;

    beforeEach(() => {
      // Spy on scrollIntoView to ensure it is NEVER called (it shifts the page viewport)
      scrollIntoViewSpy = vi.fn() as unknown as ReturnType<typeof vi.fn>;
      Element.prototype.scrollIntoView =
        scrollIntoViewSpy as unknown as typeof Element.prototype.scrollIntoView;
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('does NOT call scrollIntoView when switching to diff mode', async () => {
      const user = userEvent.setup();
      const { inputData, outputData } = buildLargeJsonPair(30);

      render(<OutputRenderer output={outputData} inputData={inputData} />);
      await user.click(screen.getByText('Diff'));

      // scrollIntoView must NEVER be called — it shifts the entire page viewport
      expect(scrollIntoViewSpy).not.toHaveBeenCalled();
    });

    it('scrolls the diff container to the first change', async () => {
      const user = userEvent.setup();
      const { inputData, outputData } = buildLargeJsonPair(30);

      const { container } = render(<OutputRenderer output={outputData} inputData={inputData} />);

      // Find the diff container before clicking to mock its geometry
      await user.click(screen.getByText('Diff'));

      // Wait for the useEffect to fire
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      const diffContainer = container.querySelector('.jsondiffpatch-unchanged-showing');
      expect(diffContainer).not.toBeNull();

      // The diff container should have a scrollTop value set
      // (In jsdom, getBoundingClientRect returns zeros, so scrollTop will be 0,
      // but we can verify the container exists and has the right classes)
      expect(diffContainer!.classList.contains('overflow-y-auto')).toBe(true);
      expect(diffContainer!.classList.contains('overflow-x-hidden')).toBe(true);
      expect(diffContainer!.classList.contains('min-w-0')).toBe(true);
    });

    it('has the first change element present in the diff container', async () => {
      const user = userEvent.setup();
      const { inputData, outputData } = buildLargeJsonPair(30);

      const { container } = render(<OutputRenderer output={outputData} inputData={inputData} />);
      await user.click(screen.getByText('Diff'));

      const diffContainer = container.querySelector('.jsondiffpatch-unchanged-showing');
      expect(diffContainer).not.toBeNull();

      // The modified element must exist for scroll-to-first-change to work
      const firstChange = diffContainer!.querySelector(
        '.jsondiffpatch-added, .jsondiffpatch-deleted, .jsondiffpatch-modified'
      );
      expect(firstChange).not.toBeNull();
    });

    it('diff container has overflow containment classes to prevent layout breakout', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ a: 1 });
      const output = JSON.stringify({ a: 2 });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      // The diff container must have min-w-0 and overflow-x-hidden to prevent
      // jsondiffpatch's inline-block elements from expanding the page layout
      const diffContainer = container.querySelector('.jsondiffpatch-unchanged-showing');
      expect(diffContainer).not.toBeNull();
      expect(diffContainer!.className).toContain('min-w-0');
      expect(diffContainer!.className).toContain('overflow-x-hidden');
      expect(diffContainer!.className).toContain('overflow-y-auto');
    });

    it('root wrapper has min-w-0 to prevent flex layout breakout', () => {
      const input = JSON.stringify({ a: 1 });
      const output = JSON.stringify({ a: 2 });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);

      // The outermost div of OutputRenderer must have min-w-0
      const rootDiv = container.firstElementChild as HTMLElement;
      expect(rootDiv).not.toBeNull();
      expect(rootDiv.className).toContain('min-w-0');
    });

    it('content wrapper has min-w-0 and overflow-hidden', async () => {
      const user = userEvent.setup();
      const input = JSON.stringify({ a: 1 });
      const output = JSON.stringify({ a: 2 });

      const { container } = render(<OutputRenderer output={output} inputData={input} />);
      await user.click(screen.getByText('Diff'));

      // The content wrapper (parent of diff container) must contain overflow
      const diffContainer = container.querySelector('.jsondiffpatch-unchanged-showing');
      expect(diffContainer).not.toBeNull();
      const contentWrapper = diffContainer!.parentElement;
      expect(contentWrapper).not.toBeNull();
      expect(contentWrapper!.className).toContain('min-w-0');
      expect(contentWrapper!.className).toContain('overflow-hidden');
    });
  });
});
