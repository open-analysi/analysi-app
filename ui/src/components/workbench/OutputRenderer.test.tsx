import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { OutputRenderer } from './OutputRenderer';

describe('OutputRenderer', () => {
  describe('explicit isError prop', () => {
    it('should show ERROR when isError prop is true', () => {
      const output = JSON.stringify({ result: 'some data' });

      render(<OutputRenderer output={output} isError={true} />);

      expect(screen.getByText('ERROR')).toBeInTheDocument();
    });

    it('should NOT show ERROR when isError prop is false', () => {
      const output = JSON.stringify({ result: 'some data' });

      render(<OutputRenderer output={output} isError={false} />);

      expect(screen.queryByText('ERROR')).not.toBeInTheDocument();
    });

    it('should NOT show ERROR by default (isError defaults to false)', () => {
      const output = JSON.stringify({ result: 'some data' });

      render(<OutputRenderer output={output} />);

      expect(screen.queryByText('ERROR')).not.toBeInTheDocument();
    });

    it('should NOT show ERROR for JSON containing word "error" when isError is false', () => {
      // This is a successful task output that happens to contain the word "error"
      // in its analysis text (describing security incidents)
      const successfulOutput = JSON.stringify({
        alert_id: 'd9ddfa55-8599-430f-babc-c3960404a3c1',
        title: 'PowerShell Found in Requested URL',
        enrichments: {
          alert_detailed_analysis: {
            ai_analysis: 'No errors detected in the system. The attack was blocked successfully.',
          },
        },
      });

      render(<OutputRenderer output={successfulOutput} isError={false} />);

      // Should NOT show the ERROR label because isError is explicitly false
      expect(screen.queryByText('ERROR')).not.toBeInTheDocument();
    });

    it('should show ERROR for actual error JSON when isError is true', () => {
      const errorOutput = JSON.stringify({
        error: 'Task execution failed: timeout exceeded',
        status: 'failed',
      });

      render(<OutputRenderer output={errorOutput} isError={true} />);

      expect(screen.getByText('ERROR')).toBeInTheDocument();
    });
  });

  describe('output rendering', () => {
    it('should show placeholder when output is empty', () => {
      render(<OutputRenderer output="" />);

      expect(
        screen.getByText('Output will appear here after running the task')
      ).toBeInTheDocument();
    });

    it('should show placeholder when output is whitespace only', () => {
      render(<OutputRenderer output="   " />);

      expect(
        screen.getByText('Output will appear here after running the task')
      ).toBeInTheDocument();
    });

    it('should render JSON output prettified', () => {
      const output = JSON.stringify({ key: 'value', nested: { a: 1 } });

      render(<OutputRenderer output={output} />);

      // Check that the output is rendered (prettified JSON)
      expect(screen.getByText(/"key": "value"/)).toBeInTheDocument();
    });

    it('should render plain text output as-is', () => {
      const output = 'This is plain text output';

      render(<OutputRenderer output={output} />);

      expect(screen.getByText(output)).toBeInTheDocument();
    });
  });

  describe('copy functionality', () => {
    it('should show Copy button when onCopy is provided', () => {
      render(<OutputRenderer output="test" onCopy={() => {}} />);

      expect(screen.getByText('Copy')).toBeInTheDocument();
    });

    it('should show Copied text when isCopied is true', () => {
      render(<OutputRenderer output="test" onCopy={() => {}} isCopied={true} />);

      expect(screen.getByText('✓ Copied')).toBeInTheDocument();
    });
  });
});
