import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { Workflow } from '../../../types/workflow';
import { WorkflowExecutionDialog } from '../WorkflowExecutionDialog';

describe('WorkflowExecutionDialog - Input Data Handling', () => {
  const mockOnClose = vi.fn();
  const mockOnExecute = vi.fn();
  const INPUT_PLACEHOLDER = 'Enter JSON input data...';

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const createMockWorkflow = (dataSamples?: any[]): Workflow =>
    ({
      id: 'test-workflow-123',
      tenant_id: 'test-tenant',
      name: 'Test Workflow',
      description: 'Test workflow for input handling',
      is_dynamic: false,
      io_schema: {
        input: {
          type: 'object',
          properties: {
            title: { type: 'string' },
            severity: { type: 'string' },
          },
        },
        output: {
          type: 'object',
          properties: {},
        },
      },
      data_samples: dataSamples,
      status: 'enabled',
      created_by: 'test-user',
      created_at: '2025-01-20T00:00:00Z',
      planner_id: null,
      nodes: [],
      edges: [],
    }) as unknown as Workflow;

  describe('Wrapped Data Samples (New Convention)', () => {
    it('should extract input field from wrapped data sample on initialization', async () => {
      const workflow = createMockWorkflow([
        {
          name: 'Test Sample 1',
          input: {
            title: 'Test Alert',
            severity: 'high',
          },
          description: 'Test description',
          expected_output: { result: 'success' },
        },
      ]);

      render(
        <WorkflowExecutionDialog
          isOpen={true}
          workflow={workflow}
          onClose={mockOnClose}
          onExecute={mockOnExecute}
        />
      );

      // Wait for the component to initialize
      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);
        expect(textarea).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);

      // Verify only the input field is shown, not the wrapper
      const parsedValue = JSON.parse((textarea as HTMLTextAreaElement).value);
      expect(parsedValue).toEqual({
        title: 'Test Alert',
        severity: 'high',
      });

      // Should NOT include wrapper fields
      expect(parsedValue).not.toHaveProperty('name');
      expect(parsedValue).not.toHaveProperty('description');
      expect(parsedValue).not.toHaveProperty('expected_output');
    });

    it('should extract input field when selecting different samples from dropdown', async () => {
      const workflow = createMockWorkflow([
        {
          name: 'Sample 1',
          input: { title: 'Alert 1', severity: 'low' },
          description: 'First sample',
          expected_output: {},
        },
        {
          name: 'Sample 2',
          input: { title: 'Alert 2', severity: 'critical' },
          description: 'Second sample',
          expected_output: {},
        },
      ]);

      render(
        <WorkflowExecutionDialog
          isOpen={true}
          workflow={workflow}
          onClose={mockOnClose}
          onExecute={mockOnExecute}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('combobox')).toBeInTheDocument();
      });

      const dropdown = screen.getByRole('combobox');
      const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);

      // Initially shows first sample's input
      let parsedValue = JSON.parse((textarea as HTMLTextAreaElement).value);
      expect(parsedValue).toEqual({ title: 'Alert 1', severity: 'low' });

      // Select second sample
      fireEvent.change(dropdown, { target: { value: '1' } });

      await waitFor(() => {
        parsedValue = JSON.parse(
          screen.getByPlaceholderText<HTMLTextAreaElement>(INPUT_PLACEHOLDER).value
        );
        expect(parsedValue).toEqual({ title: 'Alert 2', severity: 'critical' });
      });

      // Should NOT include wrapper fields
      expect(parsedValue).not.toHaveProperty('name');
      expect(parsedValue).not.toHaveProperty('description');
    });

    it('should show descriptive labels from sample.name in dropdown', async () => {
      const workflow = createMockWorkflow([
        {
          name: 'Exchange CVE Exploitation - Critical',
          input: { title: 'CVE Alert', severity: 'critical' },
          description: 'Critical vulnerability',
          expected_output: {},
        },
        {
          name: 'Brute Force Login Attempt',
          input: { title: 'Login Alert', severity: 'medium' },
          description: 'Suspicious login',
          expected_output: {},
        },
      ]);

      render(
        <WorkflowExecutionDialog
          isOpen={true}
          workflow={workflow}
          onClose={mockOnClose}
          onExecute={mockOnExecute}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('combobox')).toBeInTheDocument();
      });

      // Check that dropdown options use sample.name
      expect(screen.getByText('Exchange CVE Exploitation - Critical')).toBeInTheDocument();
      expect(screen.getByText('Brute Force Login Attempt')).toBeInTheDocument();
    });
  });

  describe('Legacy Data Samples (Unwrapped)', () => {
    it('should handle legacy workflows with unwrapped data samples', async () => {
      const workflow = createMockWorkflow([
        {
          title: 'Legacy Alert',
          severity: 'medium',
          timestamp: '2025-01-20T00:00:00Z',
        },
      ]);

      render(
        <WorkflowExecutionDialog
          isOpen={true}
          workflow={workflow}
          onClose={mockOnClose}
          onExecute={mockOnExecute}
        />
      );

      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);
        expect(textarea).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);

      // Should use the entire sample as-is (backward compatibility)
      const parsedValue = JSON.parse((textarea as HTMLTextAreaElement).value);
      expect(parsedValue).toEqual({
        title: 'Legacy Alert',
        severity: 'medium',
        timestamp: '2025-01-20T00:00:00Z',
      });
    });

    it('should generate sample data from schema when no data_samples provided', async () => {
      const workflow = createMockWorkflow();

      render(
        <WorkflowExecutionDialog
          isOpen={true}
          workflow={workflow}
          onClose={mockOnClose}
          onExecute={mockOnExecute}
        />
      );

      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);
        expect(textarea).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);

      // Should have generated sample data
      const parsedValue = JSON.parse((textarea as HTMLTextAreaElement).value);
      expect(parsedValue).toHaveProperty('title');
      expect(parsedValue).toHaveProperty('severity');
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty input field gracefully', async () => {
      const workflow = createMockWorkflow([
        {
          name: 'Empty Input Sample',
          input: {}, // Empty input object
          description: 'Sample with empty input',
          expected_output: {},
        },
      ]);

      render(
        <WorkflowExecutionDialog
          isOpen={true}
          workflow={workflow}
          onClose={mockOnClose}
          onExecute={mockOnExecute}
        />
      );

      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);
        expect(textarea).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);

      const parsedValue = JSON.parse((textarea as HTMLTextAreaElement).value);
      expect(parsedValue).toEqual({});
    });

    it('should handle sample with null input field', async () => {
      const workflow = createMockWorkflow([
        {
          name: 'Null Input Sample',
          input: null,
          description: 'Sample with null input',
          expected_output: {},
        },
      ]);

      render(
        <WorkflowExecutionDialog
          isOpen={true}
          workflow={workflow}
          onClose={mockOnClose}
          onExecute={mockOnExecute}
        />
      );

      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);
        expect(textarea).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);

      // Should fall back to the entire sample
      const parsedValue = JSON.parse((textarea as HTMLTextAreaElement).value);
      expect(parsedValue).toHaveProperty('name');
      expect(parsedValue.name).toBe('Null Input Sample');
    });

    it('should handle missing sample.name and generate default label', async () => {
      const workflow = createMockWorkflow([
        {
          input: { title: 'No name sample', severity: 'low' },
          description: 'Sample without name field',
          expected_output: {},
        },
      ]);

      render(
        <WorkflowExecutionDialog
          isOpen={true}
          workflow={workflow}
          onClose={mockOnClose}
          onExecute={mockOnExecute}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('combobox')).toBeInTheDocument();
      });

      // Should fall back to "Example 1"
      expect(screen.getByText('Example 1')).toBeInTheDocument();
    });

    it('should clear input when Clear option is selected', async () => {
      const workflow = createMockWorkflow([
        {
          name: 'Sample 1',
          input: { title: 'Test', severity: 'high' },
          description: 'Test',
          expected_output: {},
        },
      ]);

      render(
        <WorkflowExecutionDialog
          isOpen={true}
          workflow={workflow}
          onClose={mockOnClose}
          onExecute={mockOnExecute}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('combobox')).toBeInTheDocument();
      });

      const dropdown = screen.getByRole('combobox');
      const textarea = screen.getByPlaceholderText(INPUT_PLACEHOLDER);

      // Initially has data
      let parsedValue = JSON.parse((textarea as HTMLTextAreaElement).value);
      expect(parsedValue).toEqual({ title: 'Test', severity: 'high' });

      // Select clear option
      fireEvent.change(dropdown, { target: { value: '' } });

      await waitFor(() => {
        parsedValue = JSON.parse(
          screen.getByPlaceholderText<HTMLTextAreaElement>(INPUT_PLACEHOLDER).value
        );
        expect(parsedValue).toEqual({});
      });
    });
  });

  describe('Execution', () => {
    it('should pass unwrapped input data to onExecute callback', async () => {
      const workflow = createMockWorkflow([
        {
          name: 'Test Execution',
          input: { title: 'Execute Me', severity: 'critical' },
          description: 'Test execution',
          expected_output: {},
        },
      ]);

      render(
        <WorkflowExecutionDialog
          isOpen={true}
          workflow={workflow}
          onClose={mockOnClose}
          onExecute={mockOnExecute}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('Start Execution')).toBeInTheDocument();
      });

      const executeButton = screen.getByText('Start Execution');

      // Wait for button to be enabled
      await waitFor(() => {
        expect(executeButton).not.toBeDisabled();
      });

      fireEvent.click(executeButton);

      await waitFor(() => {
        expect(mockOnExecute).toHaveBeenCalledTimes(1);
        expect(mockOnExecute).toHaveBeenCalledWith({
          title: 'Execute Me',
          severity: 'critical',
        });
      });

      // Should NOT pass wrapper fields
      expect(mockOnExecute).not.toHaveBeenCalledWith(
        expect.objectContaining({
          name: expect.any(String),
          description: expect.any(String),
          expected_output: expect.any(Object),
        })
      );
    });
  });
});
