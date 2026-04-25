import React, { useEffect, useRef } from 'react';

import {
  ArrowsPointingInIcon,
  ViewfinderCircleIcon,
  CameraIcon,
} from '@heroicons/react/24/outline';
import cytoscape, { NodeSingular, Core } from 'cytoscape';
import dagre from 'cytoscape-dagre';

import {
  KdgNode,
  KdgGraph,
  KdgNodeType,
  NODE_TYPE_CONFIG,
  EDGE_TYPE_CONFIG,
  getNodeConfig,
} from '../../../types/kdg';
import UserDisplayName from '../../common/UserDisplayName';

interface KnowledgeGraphVisualizationProps {
  data: KdgGraph;
  onNodeSelect: (nodeId: string) => void;
  onNodeDoubleClick?: (nodeId: string) => void;
  selectedNodeData?: KdgNode | null;
  layoutAlgorithm?: string;
  centerNodeId?: string;
}

const MAX_LABEL_LENGTH = 30;

function truncateLabel(label: string): string {
  if (label.length <= MAX_LABEL_LENGTH) return label;
  return label.substring(0, MAX_LABEL_LENGTH - 1) + '…';
}

function formatEdgeType(type: string): string {
  return type.replace(/_/g, ' ');
}

const KnowledgeGraphVisualization = React.memo(
  ({
    data,
    onNodeSelect,
    onNodeDoubleClick,
    selectedNodeData,
    layoutAlgorithm = 'concentric',
    centerNodeId,
  }: KnowledgeGraphVisualizationProps) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const cyRef = useRef<Core | null>(null);

    // Register the dagre extension
    useEffect(() => {
      if (!Object.prototype.hasOwnProperty.call(cytoscape.prototype, 'dagre')) {
        cytoscape.use(dagre);
      }
    }, []);

    // Initialize cytoscape instance once
    useEffect(() => {
      if (!containerRef.current) return;

      // Create new cytoscape instance with default styles
      cyRef.current = cytoscape({
        container: containerRef.current,
        elements: [],
        style: [
          {
            selector: 'node',
            style: {
              label: 'data(typeLabel)',
              'text-valign': 'center',
              'text-halign': 'center',
              color: 'white',
              'font-size': '16px',
              'font-weight': 'bold',
              'background-color': '#666',
              width: '80px',
              height: '80px',
              shape: 'round-rectangle',
            },
          },
          {
            selector: 'edge',
            style: {
              'curve-style': 'bezier',
              width: 2,
              'line-color': '#ccc',
              'target-arrow-color': '#ccc',
              'target-arrow-shape': 'triangle',
            },
          },
        ],
        minZoom: 0.02,
        maxZoom: 2,
        zoomingEnabled: true,
        userZoomingEnabled: true,
        panningEnabled: true,
        userPanningEnabled: true,
        boxSelectionEnabled: true,
        selectionType: 'single',
        touchTapThreshold: 8,
        desktopTapThreshold: 4,
        autolock: false,
        autoungrabify: false,
        autounselectify: false,
        wheelSensitivity: 0.2,
      });

      // Setup event handlers for the graph
      const cy = cyRef.current;

      // Node click event
      cy.on('tap', 'node', (evt) => {
        const node = evt.target as NodeSingular;
        const nodeId = node.id();

        // Highlight the selected node
        cy.elements().removeClass('highlighted');
        node.addClass('highlighted');

        onNodeSelect(nodeId);
      });

      // Reset selection when clicking on background
      cy.on('tap', (evt) => {
        if (evt.target === cy) {
          // Clear selection if clicking on background
          cy.elements().removeClass('highlighted');
          onNodeSelect('');
        }
      });

      // Cleanup function
      return () => {
        if (cyRef.current) {
          // Remove all event listeners first
          cyRef.current.removeAllListeners();
          // Then destroy the instance
          cyRef.current.destroy();
          cyRef.current = null;
        }
      };
    }, [onNodeSelect]); // Only recreate Cytoscape instance if onNodeSelect changes

    // Update the graph data when data changes
    useEffect(() => {
      if (!cyRef.current || !data || !data.nodes || !data.edges) return;

      // Define node type icons with absolute paths to SVG files
      const nodeIcons: Record<KdgNodeType, string> = {
        task: 'url(/src/assets/icons/task.svg)',
        document: 'url(/src/assets/icons/document.svg)',
        table: 'url(/src/assets/icons/table.svg)',
        tool: 'url(/src/assets/icons/tool.svg)',
        index: 'url(/src/assets/icons/index.svg)',
        knowledge_module: 'url(/src/assets/icons/knowledge_module.svg)',
        skill: 'url(/src/assets/icons/skill.svg)',
      };

      // Build node type labels from centralized config
      const nodeTypeLabels: Record<string, string> = Object.fromEntries(
        Object.entries(NODE_TYPE_CONFIG).map(([type, config]) => [
          type,
          config.label.length > 6 ? config.label.substring(0, 6) : config.label,
        ])
      );

      // Transform the data into the format expected by Cytoscape.js
      const elements: { data: Record<string, unknown>; classes: string }[] = [
        ...data.nodes.map((node) => ({
          data: {
            id: node.id,
            label: truncateLabel(node.label),
            fullLabel: node.label,
            type: node.type,
            nodeData: node.data,
            typeLabel: nodeTypeLabels[node.type] || 'Unknown',
            icon: nodeIcons[node.type] || '',
          },
          classes: node.id === centerNodeId ? `${node.type} center-node` : node.type,
        })),
        ...data.edges.map((edge) => ({
          data: {
            id: `${edge.source}-${edge.target}`,
            source: edge.source,
            target: edge.target,
            type: edge.type,
            edgeLabel: formatEdgeType(edge.type),
          },
          classes: edge.type,
        })),
      ];

      try {
        // Destroy and recreate the cytoscape instance to ensure styles apply
        if (cyRef.current) {
          cyRef.current.destroy();
        }

        // Create fresh cytoscape instance
        cyRef.current = cytoscape({
          container: containerRef.current,
          elements: [],
          minZoom: 0.02,
          maxZoom: 2,
          zoomingEnabled: true,
          userZoomingEnabled: true,
          panningEnabled: true,
          userPanningEnabled: true,
          boxSelectionEnabled: true,
          selectionType: 'single',
          touchTapThreshold: 8,
          desktopTapThreshold: 4,
          autolock: false,
          autoungrabify: false,
          autounselectify: false,
          wheelSensitivity: 0.2,
        });

        // Setup event handlers again
        const cy = cyRef.current;

        // Track pending single-click to differentiate from double-click
        let singleClickTimer: ReturnType<typeof setTimeout> | null = null;
        let pendingNodeId: string | null = null;

        // Node click event - delay to check for double-click
        cy.on('tap', 'node', (evt) => {
          const node = evt.target as NodeSingular;
          const nodeId = node.id();

          // Highlight the selected node immediately for visual feedback
          cy.elements().removeClass('highlighted');
          node.addClass('highlighted');

          // If double-click handler exists, delay the single-click action
          if (onNodeDoubleClick) {
            // Clear any pending single-click
            if (singleClickTimer) {
              clearTimeout(singleClickTimer);
            }
            pendingNodeId = nodeId;

            // Wait to see if this becomes a double-click
            singleClickTimer = setTimeout(() => {
              if (pendingNodeId === nodeId) {
                onNodeSelect(nodeId);
              }
              singleClickTimer = null;
              pendingNodeId = null;
            }, 250); // 250ms window for double-click
          } else {
            // No double-click handler, execute immediately
            onNodeSelect(nodeId);
          }
        });

        // Node double-click event for navigation
        cy.on('dbltap', 'node', (evt) => {
          const node = evt.target as NodeSingular;
          const nodeId = node.id();

          // Cancel pending single-click
          if (singleClickTimer) {
            clearTimeout(singleClickTimer);
            singleClickTimer = null;
            pendingNodeId = null;
          }

          if (onNodeDoubleClick) {
            onNodeDoubleClick(nodeId);
          }
        });

        // Reset selection when clicking on background
        cy.on('tap', (evt) => {
          if (evt.target === cy) {
            // Cancel any pending single-click
            if (singleClickTimer) {
              clearTimeout(singleClickTimer);
              singleClickTimer = null;
              pendingNodeId = null;
            }
            // Clear selection if clicking on background
            cy.elements().removeClass('highlighted');
            onNodeSelect('');
          }
        });

        // Add elements (center-node class already added in the mapping above)
        cyRef.current.add(elements);

        // Then apply styles after elements are added
        cyRef.current.style([
          // Base node style
          {
            selector: 'node',
            style: {
              width: 180,
              height: 180,
              shape: 'round-rectangle',
              'background-color': '#4b5563',
              'border-width': 2,
              'border-color': '#e5e7eb',
              'border-opacity': 0.8,
              'background-image': 'data(icon)',
              'background-fit': 'cover',
              'background-position-x': '50%',
              'background-position-y': '50%',
              'background-width': '60%',
              'background-height': '60%',
              'background-clip': 'none',
              // Add label at the bottom — truncated, wrapped
              label: 'data(label)',
              'text-valign': 'bottom',
              'text-halign': 'center',
              'text-margin-y': 10,
              'text-wrap': 'wrap',
              'text-max-width': '280px',
              color: '#ffffff',
              'font-size': 48,
              'font-weight': 'bold',
              'text-background-color': '#1f2937',
              'text-background-opacity': 0.9,
              'text-background-padding': 12 as any,
              'text-outline-width': 1,
              'text-outline-color': '#374151',
            },
          },
          // Color nodes by type - using centralized config
          ...Object.entries(NODE_TYPE_CONFIG).map(([type, config]) => ({
            selector: `node.${type}`,
            style: { 'background-color': config.color },
          })),
          // Basic edge style with relationship label
          {
            selector: 'edge',
            style: {
              width: 2,
              'line-color': '#9ca3af',
              'target-arrow-color': '#9ca3af',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              label: 'data(edgeLabel)',
              'font-size': 32,
              color: '#d1d5db',
              'text-rotation': 'autorotate',
              'text-background-color': '#111827',
              'text-background-opacity': 0.85,
              'text-background-padding': 6 as any,
              'text-background-shape': 'roundrectangle',
              'text-outline-width': 0,
            },
          },
          // Edge styles by type - using centralized config
          ...Object.entries(EDGE_TYPE_CONFIG).map(([type, config]) => ({
            selector: `edge.${type}`,
            style: {
              'line-color': config.color,
              'target-arrow-color': config.color,
              width: config.width,
              'line-style': config.style,
            },
          })),
          // Highlighted node style
          {
            selector: 'node.highlighted',
            style: {
              'border-width': 3,
              'border-color': '#f59e0b',
              'z-index': 999,
            },
          },
          // Center node style - very prominent visual indicator
          {
            selector: 'node.center-node',
            style: {
              // Make the center node larger
              width: 220,
              height: 220,
              // Thick cyan border for center node
              'border-width': 12,
              'border-color': '#22d3ee',
              'border-opacity': 1,
              'z-index': 1000,
              // Large glow effect behind the node
              'underlay-color': '#22d3ee',
              'underlay-padding': 25,
              'underlay-opacity': 0.5,
              'underlay-shape': 'ellipse',
            },
          },
        ]);

        cyRef.current.forceRender();

        // ── PageRank: size nodes by importance ──
        // Needs at least 2 nodes and 1 edge to be meaningful
        if (cy.nodes().length >= 2 && cy.edges().length >= 1) {
          const pr = cy.elements().pageRank({ dampingFactor: 0.85, precision: 0.00001 });

          // Find rank range for normalization
          let minRank = Infinity;
          let maxRank = -Infinity;
          cy.nodes().forEach((n) => {
            const r = pr.rank(n);
            if (r < minRank) minRank = r;
            if (r > maxRank) maxRank = r;
          });

          const MIN_SIZE = 100;
          const MAX_SIZE = 200;
          const CENTER_SIZE = 240;
          const rankRange = maxRank - minRank || 1;

          cy.nodes().forEach((n) => {
            // Center node keeps a fixed large size
            if (n.hasClass('center-node')) {
              n.style({ width: CENTER_SIZE, height: CENTER_SIZE });
              return;
            }
            const normalized = (pr.rank(n) - minRank) / rankRange;
            const size = Math.round(MIN_SIZE + normalized * (MAX_SIZE - MIN_SIZE));
            n.style({ width: size, height: size });
          });
        }

        // Tooltip: show full label on hover via a DOM element
        const tooltipEl = document.createElement('div');
        tooltipEl.className =
          'cy-tooltip hidden absolute z-50 px-2 py-1 text-xs text-white bg-gray-900 border border-gray-600 rounded shadow-lg pointer-events-none max-w-xs';
        containerRef.current?.appendChild(tooltipEl);

        cy.on('mouseover', 'node', (evt) => {
          const node = evt.target as NodeSingular;
          const fullLabel = node.data('fullLabel') as string;
          const label = node.data('label') as string;
          // Only show tooltip if the label was actually truncated
          if (fullLabel && fullLabel !== label) {
            const pos = evt.renderedPosition;
            tooltipEl.textContent = fullLabel;
            tooltipEl.style.left = `${pos.x + 15}px`;
            tooltipEl.style.top = `${pos.y + 15}px`;
            tooltipEl.classList.remove('hidden');
          }
        });
        cy.on('mouseout', 'node', () => {
          tooltipEl.classList.add('hidden');
        });

        // Apply the selected layout algorithm
        let layoutConfig: any = {
          name: layoutAlgorithm,
          fit: true,
          padding: 80,
          animate: false,
        };

        // Add specific configuration for different layout types
        switch (layoutAlgorithm) {
          case 'dagre': {
            layoutConfig = {
              ...layoutConfig,
              rankDir: 'TB', // Top to bottom direction
              rankSep: 220, // Distance between ranks
              nodeSep: 200, // Distance between adjacent nodes
              edgeSep: 10, // Distance between parallel edges
              spacingFactor: 1.3,
            };
            break;
          }
          case 'breadthfirst': {
            layoutConfig = {
              ...layoutConfig,
              directed: true,
              spacingFactor: 1.5,
              avoidOverlap: true,
            };
            break;
          }
          case 'circle': {
            layoutConfig = {
              ...layoutConfig,
              avoidOverlap: true,
              spacingFactor: 1,
            };
            break;
          }
          case 'concentric': {
            layoutConfig = {
              ...layoutConfig,
              levelWidth: function () {
                return 2;
              },
              minNodeSpacing: 160,
              spacingFactor: 1.2,
            };
            break;
          }
          case 'cose': {
            layoutConfig = {
              ...layoutConfig,
              nodeRepulsion: 400_000,
              idealEdgeLength: 100,
              edgeElasticity: 100,
              nestingFactor: 5,
              gravity: 80,
              numIter: 1000,
              initialTemp: 200,
              coolingFactor: 0.95,
              minTemp: 1,
            };
            break;
          }
          case 'grid': {
            layoutConfig = {
              ...layoutConfig,
              spacingFactor: 1.5,
              avoidOverlap: true,
            };
            break;
          }
          case 'random': {
            layoutConfig = {
              ...layoutConfig,
            };
            break;
          }
          case 'preset': {
            layoutConfig = {
              ...layoutConfig,
              positions: undefined, // Use existing node positions
            };
            break;
          }
        }

        const layout = cyRef.current.layout(layoutConfig);

        // After layout completes, decide viewport: fit-all for small graphs,
        // zoom-to-center for large ones (threshold: 40 nodes)
        const FIT_ALL_THRESHOLD = 40;

        layout.on('layoutstop', () => {
          if (!cyRef.current) return;

          if (cyRef.current.nodes().length <= FIT_ALL_THRESHOLD) {
            // Small graph — fit everything so the user sees the full picture
            cyRef.current.animate(
              { fit: { eles: cyRef.current.elements(), padding: 60 } },
              { duration: 400, easing: 'ease-out-cubic' }
            );
          } else if (centerNodeId) {
            // Large graph — zoom to center node so it's not overwhelming
            const centerNode = cyRef.current.getElementById(centerNodeId);
            if (centerNode.length > 0) {
              cyRef.current.animate(
                { center: { eles: centerNode }, zoom: 0.5 },
                { duration: 400, easing: 'ease-out-cubic' }
              );
            }
          }
        });

        layout.run();
      } catch (error) {
        console.error('Error updating cytoscape graph:', error);
      }
    }, [data, layoutAlgorithm, centerNodeId]);

    return (
      <div className="relative w-full h-full">
        <div ref={containerRef} className="w-full h-full bg-dark-900"></div>

        {/* Floating details panel in top left */}
        {selectedNodeData && (
          <div className="absolute top-6 left-6 w-80 max-w-[40%] border border-gray-700 rounded-lg p-3 overflow-y-auto bg-dark-800 shadow-xl z-10 max-h-[60%]">
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-sm font-medium text-white">{selectedNodeData.label}</h3>
              <button onClick={() => onNodeSelect('')} className="text-gray-300 hover:text-white">
                ✕
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="font-medium text-blue-300">Type</span>
                <p className="text-white">{getNodeConfig(selectedNodeData.type).label}</p>
              </div>
              <div>
                <span className="font-medium text-blue-300">Created by</span>
                <p className="text-white">
                  <UserDisplayName userId={selectedNodeData.data.created_by} />
                </p>
              </div>
              <div className="col-span-2">
                <span className="font-medium text-blue-300">Description</span>
                <p className="wrap-break-word text-white">{selectedNodeData.data.description}</p>
              </div>
              {selectedNodeData.data.function && (
                <div>
                  <span className="font-medium text-blue-300">Function</span>
                  <p className="capitalize text-white">
                    {selectedNodeData.data.function.replace('_', ' ')}
                  </p>
                </div>
              )}
              {selectedNodeData.data.status && (
                <div>
                  <span className="font-medium text-blue-300">Status</span>
                  <p className="capitalize text-white">{selectedNodeData.data.status}</p>
                </div>
              )}
              <div>
                <span className="font-medium text-blue-300">Last Updated</span>
                <p className="text-white">
                  {new Date(selectedNodeData.data.updated_at).toLocaleString()}
                </p>
              </div>
              {selectedNodeData.data.version && (
                <div>
                  <span className="font-medium text-blue-300">Version</span>
                  <p className="text-white">{selectedNodeData.data.version}</p>
                </div>
              )}
            </div>
            {onNodeDoubleClick && (
              <div className="mt-3 pt-2 border-t border-gray-700">
                <p className="text-xs text-gray-400 italic">
                  Double-click to explore from this node
                </p>
              </div>
            )}
          </div>
        )}

        {/* Floating controls in bottom right */}
        <div className="absolute bottom-4 right-4 flex flex-col gap-2 z-10">
          <button
            onClick={() => {
              if (!cyRef.current) return;
              const png = cyRef.current.png({ full: true, scale: 2, bg: '#111827' });
              const link = document.createElement('a');
              link.href = png;
              link.download = `knowledge-graph-${centerNodeId ? centerNodeId.substring(0, 8) : 'full'}.png`;
              link.click();
            }}
            className="p-2 bg-dark-700 hover:bg-dark-600 border border-gray-600 rounded-lg text-white shadow-lg transition-colors"
            title="Export graph as PNG"
          >
            <CameraIcon className="w-5 h-5" />
          </button>
          <button
            onClick={() => {
              if (cyRef.current) {
                cyRef.current.fit(undefined, 50);
              }
            }}
            className="p-2 bg-dark-700 hover:bg-dark-600 border border-gray-600 rounded-lg text-white shadow-lg transition-colors"
            title="Fit all nodes in view"
          >
            <ArrowsPointingInIcon className="w-5 h-5" />
          </button>
          {centerNodeId && (
            <button
              onClick={() => {
                if (cyRef.current && centerNodeId) {
                  const centerNode = cyRef.current.getElementById(centerNodeId);
                  if (centerNode.length > 0) {
                    cyRef.current.animate(
                      {
                        center: { eles: centerNode },
                        zoom: 0.5,
                      },
                      {
                        duration: 300,
                      }
                    );
                  }
                }
              }}
              className="p-2 bg-cyan-600 hover:bg-cyan-500 border border-cyan-400 rounded-lg text-white shadow-lg transition-colors"
              title="Center on selected node"
            >
              <ViewfinderCircleIcon className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>
    );
  }
);

KnowledgeGraphVisualization.displayName = 'KnowledgeGraphVisualization';

export default KnowledgeGraphVisualization;
