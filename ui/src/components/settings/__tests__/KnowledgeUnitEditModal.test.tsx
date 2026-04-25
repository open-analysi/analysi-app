import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import { useKnowledgeUnitStore } from '../../../store/knowledgeUnitStore';
import {
  DirectiveKU,
  TableKU,
  DocumentKU,
  TableSchema,
  KnowledgeUnit,
} from '../../../types/knowledge';
import { KnowledgeUnitEditModal } from '../KnowledgeUnitEditModal';

// Test constants
const TEST_TIMESTAMP = '2024-01-01T00:00:00Z';
const DISCARD_DIALOG_TITLE = 'Discard Unsaved Changes?';
const MODIFIED_NAME = 'Test Directive Modified';

// Mock ResizeObserver before any components that use it
class ResizeObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
(global as unknown as { ResizeObserver: typeof ResizeObserver }).ResizeObserver =
  ResizeObserverMock as unknown as typeof ResizeObserver;

// Mock the backend API
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    updateDirective: vi.fn(),
    updateTable: vi.fn(),
    updateDocument: vi.fn(),
  },
}));

// Mock the store
vi.mock('../../../store/knowledgeUnitStore');

// Mock the error handler
vi.mock('../../../hooks/useErrorHandler', () => ({
  default: vi.fn(() => ({
    error: { hasError: false, message: '', context: {} },
    handleError: vi.fn(),
    createContext: vi.fn(),
    runSafe: vi.fn(async (promise: Promise<unknown>) => {
      try {
        const result = await promise;
        return [result, null];
      } catch (error) {
        return [null, error];
      }
    }),
    clearError: vi.fn(),
  })),
}));

describe('KnowledgeUnitEditModal', () => {
  const mockOnClose = vi.fn();
  const mockOnSave = vi.fn();
  const mockUpdateKnowledgeUnit = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useKnowledgeUnitStore).mockReturnValue({
      updateKnowledgeUnit: mockUpdateKnowledgeUnit,
    } as ReturnType<typeof useKnowledgeUnitStore>);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const mockDirective = {
    id: 'directive-1',
    name: 'Test Directive',
    description: 'Test directive description',
    type: 'directive',
    content: 'Original directive content',
    status: 'active',
    version: '1.0.0',
    created_by: 'test-user',
    created_at: TEST_TIMESTAMP,
    updated_at: TEST_TIMESTAMP,
    editable: true,
  } as DirectiveKU;

  const mockTable = {
    id: 'table-1',
    name: 'Test Table',
    description: 'Test table description',
    type: 'table',
    content: {
      columns: ['Column1', 'Column2'],
      data: [
        ['Row1Col1', 'Row1Col2'],
        ['Row2Col1', 'Row2Col2'],
      ],
    },
    status: 'active',
    version: '1.0.0',
    created_by: 'test-user',
    created_at: TEST_TIMESTAMP,
    updated_at: TEST_TIMESTAMP,
    editable: true,
  } as TableKU;

  const mockDocument = {
    id: 'doc-1',
    name: 'Test Document',
    description: 'Test document description',
    type: 'document',
    content: 'Original document content',
    status: 'active',
    version: '1.0.0',
    created_by: 'test-user',
    created_at: TEST_TIMESTAMP,
    updated_at: TEST_TIMESTAMP,
    editable: true,
  } as DocumentKU;

  /**
   * Renders the modal and waits for Headless UI Dialog's async transitions to settle.
   * This prevents React act() warnings from Dialog's internal state updates.
   */
  async function renderModal(ku: KnowledgeUnit | null, props?: { isOpen?: boolean }) {
    const result = render(
      <KnowledgeUnitEditModal
        isOpen={props?.isOpen ?? true}
        onClose={mockOnClose}
        knowledgeUnit={ku}
        onSave={mockOnSave}
      />
    );
    // Wait for Headless UI Dialog to finish its mount transitions
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    return result;
  }

  describe('Basic functionality', () => {
    it('should not render when knowledgeUnit is null', async () => {
      const { container } = await renderModal(null);
      expect(container.firstChild).toBeNull();
    });

    it('should render modal when open with a knowledge unit', async () => {
      await renderModal(mockDirective);

      expect(screen.getByText('Edit Directive: Test Directive')).toBeInTheDocument();
      expect(screen.getByLabelText('Name')).toHaveValue('Test Directive');
      expect(screen.getByLabelText('Description')).toHaveValue('Test directive description');
    });

    it('should close modal on Cancel button click', async () => {
      await renderModal(mockDirective);

      fireEvent.click(screen.getByText('Cancel'));
      expect(mockOnClose).toHaveBeenCalledOnce();
    });

    it('should close modal when X button is clicked', async () => {
      await renderModal(mockDirective);

      // The X button is next to the title
      const xButtons = screen.getAllByRole('button');
      const xCloseButton = xButtons.find(
        (btn) => btn.querySelector('svg') && btn.className.includes('text-gray-400')
      );
      expect(xCloseButton).toBeDefined();
      fireEvent.click(xCloseButton!);

      expect(mockOnClose).toHaveBeenCalledOnce();
    });
  });

  describe('Directive editing', () => {
    it('should render directive form with content field', async () => {
      await renderModal(mockDirective);

      const contentField = screen.getByLabelText('Content');
      expect(contentField).toBeInTheDocument();
      expect(contentField).toHaveValue('Original directive content');
      expect(contentField.tagName).toBe('TEXTAREA');
    });

    it('should update directive successfully', async () => {
      vi.mocked(backendApi.updateDirective).mockResolvedValue({
        ...mockDirective,
        name: 'Updated Directive',
      });

      await renderModal(mockDirective);

      const nameInput = screen.getByLabelText('Name');
      await userEvent.clear(nameInput);
      await userEvent.type(nameInput, 'Updated Directive');

      fireEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(backendApi.updateDirective).toHaveBeenCalledWith('directive-1', {
          name: 'Updated Directive',
          description: 'Test directive description',
          content: 'Original directive content',
        });
        expect(mockUpdateKnowledgeUnit).toHaveBeenCalled();
        expect(mockOnSave).toHaveBeenCalled();
        expect(mockOnClose).toHaveBeenCalled();
      });
    });
  });

  describe('Document editing', () => {
    it('should render document form with content field', async () => {
      await renderModal(mockDocument);

      const contentField = screen.getByLabelText('Content');
      expect(contentField).toBeInTheDocument();
      expect(contentField).toHaveValue('Original document content');
      expect(contentField.tagName).toBe('TEXTAREA');
    });

    it('should show character and line count for document', async () => {
      await renderModal(mockDocument);

      expect(screen.getByText(/25 characters • 1 lines/)).toBeInTheDocument();
    });

    it('should update document successfully', async () => {
      vi.mocked(backendApi.updateDocument).mockResolvedValue({
        ...mockDocument,
        content: 'Updated content',
      });

      await renderModal(mockDocument);

      const contentField = screen.getByLabelText('Content');
      await userEvent.clear(contentField);
      await userEvent.type(contentField, 'Updated content');

      fireEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(backendApi.updateDocument).toHaveBeenCalledWith('doc-1', {
          name: 'Test Document',
          description: 'Test document description',
          content: 'Updated content',
        });
        expect(mockUpdateKnowledgeUnit).toHaveBeenCalled();
        expect(mockOnSave).toHaveBeenCalled();
        expect(mockOnClose).toHaveBeenCalled();
      });
    });
  });

  describe('Table editing', () => {
    it('should render table form with editable cells', async () => {
      await renderModal(mockTable);

      expect(screen.getByText('Table Data')).toBeInTheDocument();

      // Check column headers are editable
      const columnInputs = screen.getAllByDisplayValue(/Column/);
      expect(columnInputs).toHaveLength(2);

      // Check data cells are present
      expect(screen.getByDisplayValue('Row1Col1')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Row1Col2')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Row2Col1')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Row2Col2')).toBeInTheDocument();
    });

    it('should add a new row to table', async () => {
      await renderModal(mockTable);

      const addRowButton = screen.getByText('Add Row');
      fireEvent.click(addRowButton);

      // Should now have 3 rows (2 original + 1 new)
      const rows = screen.getAllByRole('row');
      // +1 for header row
      expect(rows).toHaveLength(4);
    });

    it('should remove a row from table', async () => {
      await renderModal(mockTable);

      // Find all table rows (excluding header)
      const rows = screen.getAllByRole('row');
      // rows[0] is the header with column names
      // rows[1] is the first data row

      // Find the trash icon button in the first data row
      const firstDataRow = rows[1];
      const trashButton = within(firstDataRow).getByRole('button');

      fireEvent.click(trashButton);

      // Should now have 1 data row (removed one of the two)
      await waitFor(() => {
        expect(screen.queryByDisplayValue('Row1Col1')).not.toBeInTheDocument();
        expect(screen.getByDisplayValue('Row2Col1')).toBeInTheDocument();
      });
    });

    it('should add a new column to table', async () => {
      await renderModal(mockTable);

      // Find the "+" button to add a column (it's in the header row)
      const headerRow = screen.getAllByRole('row')[0];
      const addColumnButtons = within(headerRow).getAllByRole('button');
      // The last button in the header should be the add column button (has PlusIcon)
      const addColumnButton = addColumnButtons.at(-1);

      fireEvent.click(addColumnButton!);

      // Find the input field that appears for the new column name
      const columnNameInput = within(headerRow).getByPlaceholderText('Column name');
      await userEvent.type(columnNameInput, 'NewColumn');

      // Find and click the confirm button (CheckIcon)
      const confirmButton = within(headerRow)
        .getAllByRole('button')
        .find((btn) => btn.querySelector('svg')?.querySelector('path[stroke-linecap="round"]'));
      fireEvent.click(confirmButton!);

      await waitFor(() => {
        expect(screen.getByDisplayValue('NewColumn')).toBeInTheDocument();
      });
    });

    it('should cancel adding a new column', async () => {
      await renderModal(mockTable);

      // Click add column button
      const headerRow = screen.getAllByRole('row')[0];
      const addColumnButtons = within(headerRow).getAllByRole('button');
      const addColumnButton = addColumnButtons.at(-1);
      fireEvent.click(addColumnButton!);

      // Column name input should appear
      expect(within(headerRow).getByPlaceholderText('Column name')).toBeInTheDocument();

      // Click cancel (XMarkIcon button)
      const cancelButton = within(headerRow)
        .getAllByRole('button')
        .find((btn) => {
          const svg = btn.querySelector('svg');
          return svg && btn.className.includes('text-gray-500');
        });
      fireEvent.click(cancelButton!);

      // Column name input should be gone
      expect(within(headerRow).queryByPlaceholderText('Column name')).not.toBeInTheDocument();
    });

    it('should add a new column via Enter key', async () => {
      await renderModal(mockTable);

      // Click add column button
      const headerRow = screen.getAllByRole('row')[0];
      const addColumnButtons = within(headerRow).getAllByRole('button');
      const addColumnButton = addColumnButtons.at(-1);
      fireEvent.click(addColumnButton!);

      // Type column name and press Enter
      const columnNameInput = within(headerRow).getByPlaceholderText('Column name');
      await userEvent.type(columnNameInput, 'EnterColumn');
      fireEvent.keyDown(columnNameInput, { key: 'Enter', code: 'Enter' });

      await waitFor(() => {
        expect(screen.getByDisplayValue('EnterColumn')).toBeInTheDocument();
      });
    });

    it('should remove a column from table', async () => {
      await renderModal(mockTable);

      // Both columns should be present
      expect(screen.getByDisplayValue('Column1')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Column2')).toBeInTheDocument();

      // Find the trash button next to Column1 header
      const headerRow = screen.getAllByRole('row')[0];
      const trashButtons = within(headerRow).getAllByRole('button');
      // First trash button removes Column1
      const col1TrashButton = trashButtons.find((btn) => btn.className.includes('text-red-500'));
      fireEvent.click(col1TrashButton!);

      // Column1 and its data should be gone
      await waitFor(() => {
        expect(screen.queryByDisplayValue('Column1')).not.toBeInTheDocument();
        expect(screen.queryByDisplayValue('Row1Col1')).not.toBeInTheDocument();
        expect(screen.queryByDisplayValue('Row2Col1')).not.toBeInTheDocument();
        // Column2 and its data should remain
        expect(screen.getByDisplayValue('Column2')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Row1Col2')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Row2Col2')).toBeInTheDocument();
      });
    });

    it('should update column name', async () => {
      await renderModal(mockTable);

      const col1Input = screen.getByDisplayValue('Column1');
      await userEvent.clear(col1Input);
      await userEvent.type(col1Input, 'RenamedColumn');

      expect(screen.getByDisplayValue('RenamedColumn')).toBeInTheDocument();
    });

    it('should update table cell value', async () => {
      await renderModal(mockTable);

      const cellInput = screen.getByDisplayValue('Row1Col1');
      await userEvent.clear(cellInput);
      await userEvent.type(cellInput, 'Updated Value');

      expect(cellInput).toHaveValue('Updated Value');
    });

    it('should update table successfully', async () => {
      vi.mocked(backendApi.updateTable).mockResolvedValue({
        ...mockTable,
      });

      await renderModal(mockTable);

      fireEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(backendApi.updateTable).toHaveBeenCalledWith('table-1', {
          name: 'Test Table',
          description: 'Test table description',
          content: {
            columns: ['Column1', 'Column2'],
            data: [
              ['Row1Col1', 'Row1Col2'],
              ['Row2Col1', 'Row2Col2'],
            ],
          },
          schema: {
            columns: [
              { name: 'Column1', type: 'string' },
              { name: 'Column2', type: 'string' },
            ],
          },
        });
        expect(mockUpdateKnowledgeUnit).toHaveBeenCalled();
        expect(mockOnSave).toHaveBeenCalled();
        expect(mockOnClose).toHaveBeenCalled();
      });
    });
  });

  describe('Schema editor', () => {
    it('should toggle schema editor visibility', async () => {
      await renderModal(mockTable);

      // Schema editor should be hidden by default
      expect(screen.queryByText('Type', { selector: 'span' })).not.toBeInTheDocument();

      // Click "Show Schema" button
      fireEvent.click(screen.getByText('Show Schema'));

      // Schema type dropdowns should now be visible
      const typeLabels = screen.getAllByText('Type');
      expect(typeLabels.length).toBeGreaterThan(0);

      // Click "Hide Schema" to hide it again
      fireEvent.click(screen.getByText('Hide Schema'));
      expect(screen.queryByText('Type', { selector: 'span' })).not.toBeInTheDocument();
    });

    it('should change column type in schema editor', async () => {
      await renderModal(mockTable);

      // Show schema editor
      fireEvent.click(screen.getByText('Show Schema'));

      // All columns should default to "string" type
      const selects = screen.getAllByRole('combobox');
      expect(selects).toHaveLength(2); // One per column
      expect(selects[0]).toHaveValue('string');

      // Change first column type to "number"
      fireEvent.change(selects[0], { target: { value: 'number' } });
      expect(selects[0]).toHaveValue('number');
    });

    it('should load existing TableSchema correctly', async () => {
      const tableWithSchema = {
        ...mockTable,
        schema: {
          columns: [
            { name: 'Column1', type: 'number' },
            { name: 'Column2', type: 'boolean' },
          ],
        } as TableSchema,
      };

      await renderModal(tableWithSchema);

      // Show schema editor
      fireEvent.click(screen.getByText('Show Schema'));

      const selects = screen.getAllByRole('combobox');
      expect(selects[0]).toHaveValue('number');
      expect(selects[1]).toHaveValue('boolean');
    });
  });

  describe('Table dual-format support', () => {
    it('should handle table content in Format 1 (columns + data arrays)', async () => {
      const tableFormat1 = {
        id: 'table-format1',
        name: 'Feedback Table',
        description: 'Format 1 table',
        type: 'table',
        content: {
          columns: ['test', 'one', 'two'],
          data: [
            ['val1', 'val2', 'val3'],
            ['val4', 'val5', 'val6'],
          ],
        },
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      } as TableKU;

      await renderModal(tableFormat1);

      // Should display column headers
      expect(screen.getByDisplayValue('test')).toBeInTheDocument();
      expect(screen.getByDisplayValue('one')).toBeInTheDocument();
      expect(screen.getByDisplayValue('two')).toBeInTheDocument();

      // Should display data cells
      expect(screen.getByDisplayValue('val1')).toBeInTheDocument();
      expect(screen.getByDisplayValue('val2')).toBeInTheDocument();
      expect(screen.getByDisplayValue('val3')).toBeInTheDocument();
    });

    it('should handle table content in Format 2 (rows as objects) and convert to Format 1', async () => {
      const tableFormat2 = {
        id: 'table-format2',
        name: 'Threat Actor Database',
        description: 'Format 2 table',
        type: 'table',
        content: {
          rows: [
            { name: 'Lazarus Group', type: 'APT', sophistication: 'advanced' },
            { name: 'FIN7', type: 'Ransomware', sophistication: 'advanced' },
          ],
        } as unknown as TableKU['content'],
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      } as TableKU;

      await renderModal(tableFormat2);

      // Should convert to Format 1 and display column headers
      expect(screen.getByDisplayValue('name')).toBeInTheDocument();
      expect(screen.getByDisplayValue('type')).toBeInTheDocument();
      expect(screen.getByDisplayValue('sophistication')).toBeInTheDocument();

      // Should display converted data
      expect(screen.getByDisplayValue('Lazarus Group')).toBeInTheDocument();
      expect(screen.getByDisplayValue('APT')).toBeInTheDocument();
      expect(screen.getAllByDisplayValue('advanced')).toHaveLength(2); // Both rows have 'advanced' sophistication
      expect(screen.getByDisplayValue('FIN7')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Ransomware')).toBeInTheDocument();
    });

    it('should handle arrays in table cells by converting to JSON strings', async () => {
      const tableWithArrays = {
        id: 'table-with-arrays',
        name: 'Table with Arrays',
        description: 'Table containing array values',
        type: 'table',
        content: {
          rows: [
            {
              name: 'Lazarus Group',
              ttps: ['spear-phishing', 'supply-chain', 'zero-day'],
              targets: ['financial', 'cryptocurrency'],
            },
            {
              name: 'FIN7',
              ttps: ['pos-malware', 'social-engineering'],
              targets: ['retail', 'hospitality'],
            },
          ],
        } as unknown as TableKU['content'],
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      } as TableKU;

      await renderModal(tableWithArrays);

      // Arrays should be converted to JSON strings
      expect(
        screen.getByDisplayValue('["spear-phishing","supply-chain","zero-day"]')
      ).toBeInTheDocument();
      expect(screen.getByDisplayValue('["financial","cryptocurrency"]')).toBeInTheDocument();
      expect(screen.getByDisplayValue('["pos-malware","social-engineering"]')).toBeInTheDocument();
      expect(screen.getByDisplayValue('["retail","hospitality"]')).toBeInTheDocument();
    });

    it('should handle empty table in Format 2', async () => {
      const emptyTableFormat2 = {
        id: 'table-empty-format2',
        name: 'Empty Table',
        description: 'Empty Format 2 table',
        type: 'table',
        content: {
          rows: [],
        } as unknown as TableKU['content'],
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      } as TableKU;

      await renderModal(emptyTableFormat2);

      // Should initialize with empty columns and data
      expect(screen.getByText('Table Data')).toBeInTheDocument();
      // The Save button should be disabled because there are no columns
      const saveButton = screen.getByText('Save');
      expect(saveButton).toBeDisabled();
    });

    it('should handle table with only columns but no rows in Format 2', async () => {
      const tableFormat2NoRows = {
        id: 'table-format2-no-rows',
        name: 'Table No Rows',
        description: 'Format 2 table with no rows',
        type: 'table',
        content: {
          rows: [
            { col1: '', col2: '', col3: '' }, // Empty first row to establish schema
          ],
        } as unknown as TableKU['content'],
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      } as TableKU;

      await renderModal(tableFormat2NoRows);

      // Should extract column names from the first row
      expect(screen.getByDisplayValue('col1')).toBeInTheDocument();
      expect(screen.getByDisplayValue('col2')).toBeInTheDocument();
      expect(screen.getByDisplayValue('col3')).toBeInTheDocument();
    });
  });

  describe('JSON cell handling', () => {
    it('should display object values in rows-format as JSON strings, not [object Object]', async () => {
      const tableWithObjects = {
        id: 'table-json-objects',
        name: 'Table with Objects',
        description: 'Table containing object values',
        type: 'table',
        content: {
          rows: [
            {
              name: 'rule-1',
              config: { severity: 'high', enabled: true },
              tags: ['critical', 'network'],
            },
          ],
        } as unknown as TableKU['content'],
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      } as TableKU;

      await renderModal(tableWithObjects);

      // Object should be JSON.stringify'd, NOT "[object Object]"
      expect(screen.getByDisplayValue('{"severity":"high","enabled":true}')).toBeInTheDocument();
      // Array should also be JSON.stringify'd
      expect(screen.getByDisplayValue('["critical","network"]')).toBeInTheDocument();
      // Primitive value should display normally
      expect(screen.getByDisplayValue('rule-1')).toBeInTheDocument();
    });

    it('should display object values in columns+data format as JSON strings', async () => {
      const tableWithObjectData = {
        id: 'table-json-data',
        name: 'Table with JSON Data',
        description: 'columns+data format with objects',
        type: 'table',
        content: {
          columns: ['name', 'metadata'],
          data: [['item-1', { key: 'value', nested: [1, 2, 3] }]],
        } as unknown as TableKU['content'],
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      } as TableKU;

      await renderModal(tableWithObjectData);

      // Object in columns+data format should also be stringified
      expect(screen.getByDisplayValue('{"key":"value","nested":[1,2,3]}')).toBeInTheDocument();
      expect(screen.getByDisplayValue('item-1')).toBeInTheDocument();
    });

    it('should keep JSON cell value as string after blur (no [object Object] flip)', async () => {
      const tableWithJsonSchema = {
        id: 'table-json-schema',
        name: 'JSON Schema Table',
        description: 'Table with JSON column type',
        type: 'table',
        content: {
          columns: ['name', 'payload'],
          data: [['test', '{"a":1}']],
        },
        schema: {
          columns: [
            { name: 'name', type: 'string' },
            { name: 'payload', type: 'json' },
          ],
        } as TableSchema,
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      } as TableKU;

      await renderModal(tableWithJsonSchema);

      const jsonInput = screen.getByDisplayValue('{"a":1}');
      expect(jsonInput).toBeInTheDocument();

      // Edit the JSON value
      await userEvent.clear(jsonInput);
      await userEvent.type(jsonInput, '{{"b":2}');

      // Blur to trigger convertCellValue
      fireEvent.blur(jsonInput);

      // Value should remain as a string, not become [object Object]
      await waitFor(() => {
        expect(screen.getByDisplayValue('{"b":2}')).toBeInTheDocument();
      });

      // Should NOT contain [object Object]
      expect(screen.queryByDisplayValue('[object Object]')).not.toBeInTheDocument();
    });

    it('should keep array JSON cell value as string after edit and blur', async () => {
      const tableWithJsonSchema = {
        id: 'table-json-array',
        name: 'JSON Array Table',
        description: 'Table with JSON column type containing arrays',
        type: 'table',
        content: {
          columns: ['id', 'items'],
          data: [['row1', '["a","b"]']],
        },
        schema: {
          columns: [
            { name: 'id', type: 'string' },
            { name: 'items', type: 'json' },
          ],
        } as TableSchema,
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      } as TableKU;

      await renderModal(tableWithJsonSchema);

      const jsonInput = screen.getByDisplayValue('["a","b"]');

      // Edit the array — use fireEvent.change since userEvent.type treats [ as key descriptor
      fireEvent.change(jsonInput, { target: { value: '["x","y","z"]' } });

      // Blur to trigger convertCellValue
      fireEvent.blur(jsonInput);

      // Value should remain as a JSON string
      await waitFor(() => {
        expect(screen.getByDisplayValue('["x","y","z"]')).toBeInTheDocument();
      });
    });
  });

  describe('Unsaved changes handling', () => {
    it('should show ConfirmDialog when form is modified and trying to close', async () => {
      await renderModal(mockDirective);

      const nameInput = screen.getByLabelText('Name');
      // Use fireEvent instead of userEvent to avoid extra act() scope from keystroke wrapping
      fireEvent.change(nameInput, { target: { value: MODIFIED_NAME } });

      // Try to close - opens ConfirmDialog which has its own Dialog transitions
      await act(async () => {
        fireEvent.click(screen.getByText('Cancel'));
        await new Promise((r) => setTimeout(r, 0));
      });

      // ConfirmDialog should be displayed
      await waitFor(() => {
        expect(screen.getByText(DISCARD_DIALOG_TITLE)).toBeInTheDocument();
        expect(
          screen.getByText(
            'You have unsaved changes. Are you sure you want to exit? All your changes will be lost.'
          )
        ).toBeInTheDocument();
      });
    });

    it('should not show ConfirmDialog when no changes made', async () => {
      await renderModal(mockDirective);

      fireEvent.click(screen.getByText('Cancel'));

      // ConfirmDialog should NOT be displayed
      expect(screen.queryByText(DISCARD_DIALOG_TITLE)).not.toBeInTheDocument();
      expect(mockOnClose).toHaveBeenCalled();
    });

    it('should show ConfirmDialog on escape key with unsaved changes', async () => {
      await renderModal(mockDirective);

      const nameInput = screen.getByLabelText('Name');
      fireEvent.change(nameInput, { target: { value: MODIFIED_NAME } });

      // Simulate Escape key press — opens ConfirmDialog with Dialog transitions
      await act(async () => {
        fireEvent.keyDown(document, { key: 'Escape', code: 'Escape' });
        await new Promise((r) => setTimeout(r, 0));
      });

      // ConfirmDialog should be displayed
      await waitFor(() => {
        expect(screen.getByText(DISCARD_DIALOG_TITLE)).toBeInTheDocument();
      });
    });

    it('should close without ConfirmDialog on escape when no changes', async () => {
      await renderModal(mockDirective);

      // Simulate Escape key press
      fireEvent.keyDown(document, { key: 'Escape', code: 'Escape' });

      // ConfirmDialog should NOT be displayed
      expect(screen.queryByText(DISCARD_DIALOG_TITLE)).not.toBeInTheDocument();
      expect(mockOnClose).toHaveBeenCalled();
    });

    it('should close modal when Discard Changes is clicked in ConfirmDialog', async () => {
      await renderModal(mockDirective);

      const nameInput = screen.getByLabelText('Name');
      fireEvent.change(nameInput, { target: { value: MODIFIED_NAME } });

      // Try to close — opens ConfirmDialog
      await act(async () => {
        fireEvent.click(screen.getByText('Cancel'));
        await new Promise((r) => setTimeout(r, 0));
      });

      // Wait for ConfirmDialog
      await waitFor(() => {
        expect(screen.getByText(DISCARD_DIALOG_TITLE)).toBeInTheDocument();
      });

      // Click "Discard Changes" — closes both dialogs
      await act(async () => {
        fireEvent.click(screen.getByText('Discard Changes'));
        await new Promise((r) => setTimeout(r, 0));
      });

      // Modal should close
      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalled();
      });
    });

    it('should keep modal open when Keep Editing is clicked in ConfirmDialog', async () => {
      await renderModal(mockDirective);

      const nameInput = screen.getByLabelText('Name');
      fireEvent.change(nameInput, { target: { value: MODIFIED_NAME } });

      // Try to close — opens ConfirmDialog
      await act(async () => {
        fireEvent.click(screen.getByText('Cancel'));
        await new Promise((r) => setTimeout(r, 0));
      });

      // Wait for ConfirmDialog
      await waitFor(() => {
        expect(screen.getByText(DISCARD_DIALOG_TITLE)).toBeInTheDocument();
      });

      // Click "Keep Editing"
      await act(async () => {
        fireEvent.click(screen.getByText('Keep Editing'));
        await new Promise((r) => setTimeout(r, 0));
      });

      // ConfirmDialog should close, but main modal should stay open
      await waitFor(() => {
        expect(screen.queryByText(DISCARD_DIALOG_TITLE)).not.toBeInTheDocument();
      });
      expect(mockOnClose).not.toHaveBeenCalled();
      // Modal content should still be visible
      expect(screen.getByLabelText('Name')).toBeInTheDocument();
    });

    it('should show ConfirmDialog when X button is clicked with unsaved changes', async () => {
      await renderModal(mockDirective);

      const nameInput = screen.getByLabelText('Name');
      fireEvent.change(nameInput, { target: { value: MODIFIED_NAME } });

      // Click X close button — opens ConfirmDialog
      const xButtons = screen.getAllByRole('button');
      const xCloseButton = xButtons.find(
        (btn) => btn.querySelector('svg') && btn.className.includes('text-gray-400')
      );
      await act(async () => {
        fireEvent.click(xCloseButton!);
        await new Promise((r) => setTimeout(r, 0));
      });

      // ConfirmDialog should be displayed
      await waitFor(() => {
        expect(screen.getByText(DISCARD_DIALOG_TITLE)).toBeInTheDocument();
      });
      expect(mockOnClose).not.toHaveBeenCalled();
    });
  });

  describe('Form validation', () => {
    it('should disable save button when name is empty', async () => {
      await renderModal(mockDirective);

      const nameInput = screen.getByLabelText('Name');
      await userEvent.clear(nameInput);

      const saveButton = screen.getByText('Save');
      expect(saveButton).toBeDisabled();
    });

    it('should allow save when description is empty (description is optional)', async () => {
      await renderModal(mockDirective);

      const descriptionInput = screen.getByLabelText('Description');
      await userEvent.clear(descriptionInput);

      const saveButton = screen.getByText('Save');
      expect(saveButton).not.toBeDisabled();
    });

    it('should disable save button when content is empty for directive', async () => {
      await renderModal(mockDirective);

      const contentInput = screen.getByLabelText('Content');
      await userEvent.clear(contentInput);

      const saveButton = screen.getByText('Save');
      expect(saveButton).toBeDisabled();
    });

    it('should disable save button when table has no columns', async () => {
      const emptyTable = {
        ...mockTable,
        content: { columns: [], data: [] },
      };

      await renderModal(emptyTable);

      const saveButton = screen.getByText('Save');
      expect(saveButton).toBeDisabled();
    });
  });

  describe('Loading state', () => {
    const delayedResolve = () => new Promise((resolve) => setTimeout(resolve, 100));

    it('should show loading state when saving', async () => {
      vi.mocked(backendApi.updateDirective).mockImplementation(delayedResolve as never);

      await renderModal(mockDirective);

      fireEvent.click(screen.getByText('Save'));

      expect(screen.getByText('Saving...')).toBeInTheDocument();

      const cancelButton = screen.getByText('Cancel');
      expect(cancelButton).toBeDisabled();
    });
  });

  describe('Error handling', () => {
    it('should handle API error gracefully', async () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      vi.mocked(backendApi.updateDirective).mockRejectedValue(new Error('API Error'));

      await renderModal(mockDirective);

      fireEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(mockOnClose).not.toHaveBeenCalled();
        expect(mockOnSave).not.toHaveBeenCalled();
      });

      consoleErrorSpy.mockRestore();
    });

    it('should display error message when API call fails', async () => {
      vi.mocked(backendApi.updateDirective).mockRejectedValue(
        new Error('Network connection failed')
      );

      await renderModal(mockDirective);

      fireEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(screen.getByText('Save Failed')).toBeInTheDocument();
        expect(screen.getByText('Network connection failed')).toBeInTheDocument();
      });
    });

    it('should dismiss error message when X button on error banner is clicked', async () => {
      vi.mocked(backendApi.updateDirective).mockRejectedValue(new Error('Validation error'));

      await renderModal(mockDirective);

      fireEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(screen.getByText('Save Failed')).toBeInTheDocument();
      });

      // Click dismiss button on the error banner
      const dismissButton = screen.getByTestId('dismiss-error');
      fireEvent.click(dismissButton);

      await waitFor(() => {
        expect(screen.queryByText('Save Failed')).not.toBeInTheDocument();
      });
    });
  });
});
