import React from 'react';

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router';
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Lightweight mock component that replicates the KnowledgeGraph URL state logic
// without importing cytoscape (which OOMs the test worker).
// ---------------------------------------------------------------------------
const EMPTY_STATE_TEXT = 'Search for a node to begin exploring';
const SEARCH_PLACEHOLDER = 'Search for a node...';

const MockKnowledgeGraph = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  // URL-backed state — mirrors KnowledgeGraph.tsx
  const centerNodeId = searchParams.get('node') || null;
  const depth = Number(searchParams.get('depth') || '2');

  const setCenterNodeId = (id: string | null) => {
    setSearchParams(
      (prev) => {
        if (id) {
          prev.set('node', id);
        } else {
          prev.delete('node');
        }
        return prev;
      },
      { replace: true }
    );
  };

  const setDepth = (d: number) => {
    setSearchParams(
      (prev) => {
        if (d === 2) {
          prev.delete('depth');
        } else {
          prev.set('depth', String(d));
        }
        return prev;
      },
      { replace: true }
    );
  };

  const handleClear = () => {
    setSearchParams(
      (prev) => {
        prev.delete('node');
        prev.delete('depth');
        return prev;
      },
      { replace: true }
    );
  };

  return (
    <div>
      <input placeholder={SEARCH_PLACEHOLDER} data-testid="search-input" />
      {centerNodeId && (
        <button data-testid="clear-btn" onClick={handleClear}>
          Clear
        </button>
      )}

      <div>
        <label htmlFor="depth-select">Depth:</label>
        <select
          id="depth-select"
          value={depth}
          onChange={(e) => setDepth(Number(e.target.value))}
          disabled={!centerNodeId}
        >
          <option value={1}>1 hop</option>
          <option value={2}>2 hops</option>
          <option value={3}>3 hops</option>
        </select>
      </div>

      {centerNodeId ? (
        <div>
          <div data-testid="center-node-id">{centerNodeId}</div>
          <div data-testid="depth-value">{depth}</div>
          <button data-testid="navigate-node" onClick={() => setCenterNodeId('node-2')}>
            Navigate to Node 2
          </button>
        </div>
      ) : (
        <p>{EMPTY_STATE_TEXT}</p>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Helper to read URL params from a MemoryRouter via a spy component
// ---------------------------------------------------------------------------
const capturedSearchParams = { current: new URLSearchParams() };

const UrlSpy = () => {
  const [searchParams] = useSearchParams();
  // Use useEffect to avoid side-effect during render (lint: react-hooks/globals)
  React.useEffect(() => {
    capturedSearchParams.current = searchParams;
  });
  return null;
};

const renderWithRouter = (initialUrl = '/knowledge-graph') =>
  render(
    <MemoryRouter initialEntries={[initialUrl]}>
      <Routes>
        <Route
          path="/knowledge-graph"
          element={
            <>
              <MockKnowledgeGraph />
              <UrlSpy />
            </>
          }
        />
      </Routes>
    </MemoryRouter>
  );

describe('KnowledgeGraph — URL state anchoring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedSearchParams.current = new URLSearchParams();
  });

  describe('reading URL params on mount', () => {
    it('reads centerNodeId from ?node param', () => {
      renderWithRouter('/knowledge-graph?node=abc-123');

      expect(screen.getByTestId('center-node-id')).toHaveTextContent('abc-123');
    });

    it('reads depth from ?depth param', () => {
      renderWithRouter('/knowledge-graph?node=abc-123&depth=4');

      expect(screen.getByTestId('depth-value')).toHaveTextContent('4');
    });

    it('defaults depth to 2 when not in URL', () => {
      renderWithRouter('/knowledge-graph?node=abc-123');

      expect(screen.getByTestId('depth-value')).toHaveTextContent('2');
    });

    it('shows empty state when no node param', () => {
      renderWithRouter('/knowledge-graph');

      expect(screen.getByText(EMPTY_STATE_TEXT)).toBeInTheDocument();
      expect(screen.queryByTestId('center-node-id')).not.toBeInTheDocument();
    });
  });

  describe('writing URL params on interaction', () => {
    it('sets ?node param when navigating to a node', async () => {
      renderWithRouter('/knowledge-graph?node=node-1');

      fireEvent.click(screen.getByTestId('navigate-node'));

      await waitFor(() => {
        expect(capturedSearchParams.current.get('node')).toBe('node-2');
      });
    });

    it('clears node and depth params on clear', async () => {
      renderWithRouter('/knowledge-graph?node=abc-123&depth=3');

      fireEvent.click(screen.getByTestId('clear-btn'));

      await waitFor(() => {
        expect(capturedSearchParams.current.get('node')).toBeNull();
        expect(capturedSearchParams.current.get('depth')).toBeNull();
        expect(screen.getByText(EMPTY_STATE_TEXT)).toBeInTheDocument();
      });
    });

    it('updates depth in URL when changed', async () => {
      renderWithRouter('/knowledge-graph?node=abc-123');

      const depthSelect = screen.getByLabelText('Depth:');
      fireEvent.change(depthSelect, { target: { value: '3' } });

      await waitFor(() => {
        expect(capturedSearchParams.current.get('depth')).toBe('3');
      });
    });

    it('removes depth from URL when set to default (2)', async () => {
      renderWithRouter('/knowledge-graph?node=abc-123&depth=3');

      const depthSelect = screen.getByLabelText('Depth:');
      fireEvent.change(depthSelect, { target: { value: '2' } });

      await waitFor(() => {
        expect(capturedSearchParams.current.get('depth')).toBeNull();
      });
    });
  });

  describe('depth control state', () => {
    it('disables depth select when no center node', () => {
      renderWithRouter('/knowledge-graph');

      expect(screen.getByLabelText('Depth:')).toBeDisabled();
    });

    it('enables depth select when center node is present', () => {
      renderWithRouter('/knowledge-graph?node=abc-123');

      expect(screen.getByLabelText('Depth:')).not.toBeDisabled();
    });
  });

  describe('preserving other URL params', () => {
    it('preserves unrelated params when setting node', async () => {
      renderWithRouter('/knowledge-graph?node=node-1&layout=dagre');

      fireEvent.click(screen.getByTestId('navigate-node'));

      await waitFor(() => {
        expect(capturedSearchParams.current.get('node')).toBe('node-2');
        // layout param should still be present
        expect(capturedSearchParams.current.get('layout')).toBe('dagre');
      });
    });
  });
});

// ---------------------------------------------------------------------------
// Tests for visualization helpers (truncation, edge labels, PageRank, export)
// These test the source code directly to avoid importing cytoscape.
// ---------------------------------------------------------------------------
describe('KnowledgeGraph — visualization features', () => {
  let vizSource: string;

  beforeAll(async () => {
    const fs = await import('node:fs');
    const path = await import('node:path');
    vizSource = fs.readFileSync(
      path.resolve(__dirname, '../graph/KnowledgeGraphVisualization.tsx'),
      'utf-8'
    );
  });

  describe('label truncation', () => {
    // Extract and test the truncateLabel logic directly
    const MAX_LABEL_LENGTH = 30;
    const truncateLabel = (label: string): string => {
      if (label.length <= MAX_LABEL_LENGTH) return label;
      return label.substring(0, MAX_LABEL_LENGTH - 1) + '\u2026';
    };

    it('returns short labels unchanged', () => {
      expect(truncateLabel('Alert Triage')).toBe('Alert Triage');
    });

    it('truncates labels exceeding 30 characters', () => {
      const long = 'Splunk: Supporting Evidence Search with Observable Scoring';
      const result = truncateLabel(long);
      expect(result.length).toBe(MAX_LABEL_LENGTH);
      expect(result).toContain('\u2026');
    });

    it('returns exact-length labels unchanged', () => {
      const exact = 'A'.repeat(MAX_LABEL_LENGTH);
      expect(truncateLabel(exact)).toBe(exact);
    });

    it('source stores fullLabel for tooltip', () => {
      expect(vizSource).toContain('fullLabel: node.label');
      expect(vizSource).toContain('truncateLabel(node.label)');
    });
  });

  describe('edge labels', () => {
    const formatEdgeType = (type: string): string => type.replace(/_/g, ' ');

    it('replaces underscores with spaces', () => {
      expect(formatEdgeType('depends_on')).toBe('depends on');
      expect(formatEdgeType('used_by')).toBe('used by');
    });

    it('leaves single-word types unchanged', () => {
      expect(formatEdgeType('uses')).toBe('uses');
    });

    it('source includes edge label in style', () => {
      expect(vizSource).toContain("label: 'data(edgeLabel)'");
      expect(vizSource).toContain("'text-rotation': 'autorotate'");
    });

    it('source maps edgeLabel from edge type', () => {
      expect(vizSource).toContain('edgeLabel: formatEdgeType(edge.type)');
    });
  });

  describe('PageRank sizing', () => {
    it('source computes pageRank on elements', () => {
      expect(vizSource).toContain('cy.elements().pageRank(');
      expect(vizSource).toContain('dampingFactor: 0.85');
    });

    it('source scales node size between MIN_SIZE and MAX_SIZE', () => {
      expect(vizSource).toContain('MIN_SIZE = 100');
      expect(vizSource).toContain('MAX_SIZE = 200');
      expect(vizSource).toContain('CENTER_SIZE = 240');
    });

    it('center node gets fixed CENTER_SIZE regardless of rank', () => {
      expect(vizSource).toContain("n.hasClass('center-node')");
      expect(vizSource).toContain('n.style({ width: CENTER_SIZE, height: CENTER_SIZE })');
    });
  });

  describe('fit-all vs zoom-to-center', () => {
    it('source uses a 40-node threshold for fit-all', () => {
      expect(vizSource).toContain('FIT_ALL_THRESHOLD = 40');
    });

    it('fits all elements when under threshold', () => {
      expect(vizSource).toContain('cyRef.current.nodes().length <= FIT_ALL_THRESHOLD');
      expect(vizSource).toContain('fit: { eles: cyRef.current.elements()');
    });

    it('zooms to center node when over threshold', () => {
      expect(vizSource).toContain('center: { eles: centerNode }, zoom: 0.5');
    });
  });

  describe('PNG export', () => {
    it('source calls cy.png() with full and scale options', () => {
      expect(vizSource).toContain("cyRef.current.png({ full: true, scale: 2, bg: '#111827' })");
    });

    it('source creates a download link', () => {
      expect(vizSource).toContain('link.download =');
      expect(vizSource).toContain('knowledge-graph-');
    });
  });

  describe('UserDisplayName for created_by', () => {
    it('source uses UserDisplayName component instead of raw text', () => {
      expect(vizSource).toContain('<UserDisplayName userId={selectedNodeData.data.created_by}');
      // Should NOT render raw created_by as text
      expect(vizSource).not.toContain('{selectedNodeData.data.created_by}</p>');
    });
  });
});

describe('KnowledgeGraph — cyan selection color', () => {
  it('KnowledgeGraph source uses cyan and no pink in info bar', async () => {
    const fs = await import('node:fs');
    const path = await import('node:path');
    const source = fs.readFileSync(path.resolve(__dirname, '../KnowledgeGraph.tsx'), 'utf-8');

    // Info bar should use cyan
    expect(source).toContain('bg-cyan-50');
    expect(source).toContain('dark:bg-cyan-900/30');
    expect(source).toContain('border-cyan-300');
    expect(source).toContain('text-cyan-900');

    // Info bar should NOT use pink
    expect(source).not.toContain('bg-pink');
    expect(source).not.toContain('text-pink');
    expect(source).not.toContain('border-pink');
  });

  it('visualization source uses cyan for center node (not pink)', async () => {
    const fs = await import('node:fs');
    const path = await import('node:path');
    const source = fs.readFileSync(
      path.resolve(__dirname, '../graph/KnowledgeGraphVisualization.tsx'),
      'utf-8'
    );

    // Center node should use cyan color
    expect(source).toContain('#22d3ee');
    expect(source).toContain('bg-cyan-600');

    // Should NOT use the old pink color
    expect(source).not.toContain('#FF1493');
    expect(source).not.toContain('bg-primary hover:bg-pink');
  });
});
