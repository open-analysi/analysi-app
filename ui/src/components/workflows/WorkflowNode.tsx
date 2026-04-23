/* eslint-disable @typescript-eslint/no-unsafe-member-access, @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-argument, @typescript-eslint/no-explicit-any */
// Reaflow's NodeProps/NodeChildProps are heavily `any`-typed; suppressing
// the resulting warnings file-wide until upstream types improve.
import React, { useState, useCallback } from 'react';

import {
  PlayCircleIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  PauseCircleIcon,
  CodeBracketIcon,
  CubeTransparentIcon,
  ArrowsRightLeftIcon,
  ArrowRightIcon,
  ArrowsPointingInIcon,
  InboxStackIcon,
} from '@heroicons/react/24/outline';
import { ArrowPathIcon } from '@heroicons/react/24/solid';
import ReactDOM from 'react-dom';
import { Node, NodeChildProps, NodeProps } from 'reaflow';
import styled from 'styled-components';

// Styled component for the foreign object wrapper
const StyledForeignObject = styled.foreignObject.withConfig({
  shouldForwardProp: (prop) => !['status', 'kind'].includes(prop),
})<{
  status?: string;
  kind?: string;
}>`
  overflow: visible;
  pointer-events: none;
  font-family:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell',
    'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
  filter: ${({ status }) => (status === 'waiting' ? 'opacity(0.4)' : 'none')};

  * {
    font-family: inherit;
  }
`;

// Styled component for the node content - Dark theme matching UI
const NodeContent = styled.div.withConfig({
  shouldForwardProp: (prop) =>
    !['isStatic', 'isSelected', 'status', 'kind', 'templateType'].includes(prop),
})<{
  status?: string;
  kind?: string;
  isStatic?: boolean;
  isSelected?: boolean;
  templateType?: string;
}>`
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 12px;
  border-radius: 12px;
  border: 2px solid;
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  /* Dark theme backgrounds */
  background: ${({ status, isStatic }) => {
    if (isStatic) return 'rgba(30, 41, 59, 0.6)';
    switch (status) {
      case 'completed': {
        return 'rgba(16, 185, 129, 0.1)';
      }
      case 'running': {
        return 'rgba(59, 130, 246, 0.1)';
      }
      case 'failed': {
        return 'rgba(239, 68, 68, 0.1)';
      }
      case 'cancelled': {
        return 'rgba(245, 158, 11, 0.1)';
      }
      case 'paused': {
        return 'rgba(245, 158, 11, 0.12)';
      }
      case 'pending': {
        return 'rgba(107, 114, 128, 0.1)';
      }
      case 'waiting': {
        return 'rgba(30, 41, 59, 0.3)';
      }
      default: {
        return 'rgba(30, 41, 59, 0.5)';
      }
    }
  }};

  /* Neon-style borders */
  border-color: ${({ status, isStatic, isSelected, templateType }) => {
    // Selected state overrides everything
    if (isSelected) return '#b685ff';
    // Template-specific accent colors for static nodes
    if (isStatic && templateType) {
      switch (templateType) {
        case 'Identity': {
          return '#06b6d4'; // cyan
        }
        case 'Merge': {
          return '#a855f7'; // purple
        }
        case 'Collect': {
          return '#f59e0b'; // amber/orange
        }
        default: {
          return '#64748b';
        }
      }
    }
    if (isStatic) return '#64748b';
    switch (status) {
      case 'completed': {
        return '#10b981';
      }
      case 'running': {
        return '#3b82f6';
      }
      case 'failed': {
        return '#ef4444';
      }
      case 'cancelled':
      case 'paused': {
        return '#f59e0b';
      }
      case 'pending': {
        return '#6b7280';
      }
      case 'waiting': {
        return '#475569';
      }
      default: {
        return '#64748b';
      }
    }
  }};

  /* Glow effects */
  box-shadow: ${({ status, isStatic, isSelected }) => {
    if (isSelected) {
      return '0 0 24px rgba(182, 133, 255, 0.6), 0 0 48px rgba(182, 133, 255, 0.3), inset 0 0 16px rgba(182, 133, 255, 0.15)';
    }
    if (isStatic) return 'none';
    switch (status) {
      case 'completed': {
        return '0 0 20px rgba(16, 185, 129, 0.3), inset 0 0 20px rgba(16, 185, 129, 0.1)';
      }
      case 'running': {
        return '0 0 30px rgba(59, 130, 246, 0.4), inset 0 0 20px rgba(59, 130, 246, 0.1)';
      }
      case 'failed': {
        return '0 0 20px rgba(239, 68, 68, 0.3), inset 0 0 20px rgba(239, 68, 68, 0.1)';
      }
      case 'paused': {
        return '0 0 25px rgba(245, 158, 11, 0.35), inset 0 0 20px rgba(245, 158, 11, 0.1)';
      }
      default: {
        return 'none';
      }
    }
  }};

  ${({ status }) =>
    status === 'waiting' &&
    `
    border-style: dashed;
    opacity: 0.5;
  `}

  ${({ status }) =>
    status === 'running' &&
    `
    animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  `}

  ${({ status }) =>
    status === 'paused' &&
    `
    animation: pausedPulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  `}
  
  backdrop-filter: blur(8px);

  &:hover {
    transform: translateY(-2px);
    box-shadow: ${({ status }) => {
      switch (status) {
        case 'completed': {
          return '0 0 30px rgba(16, 185, 129, 0.5), inset 0 0 30px rgba(16, 185, 129, 0.2)';
        }
        case 'running': {
          return '0 0 40px rgba(59, 130, 246, 0.6), inset 0 0 30px rgba(59, 130, 246, 0.2)';
        }
        case 'failed': {
          return '0 0 30px rgba(239, 68, 68, 0.5), inset 0 0 30px rgba(239, 68, 68, 0.2)';
        }
        case 'paused': {
          return '0 0 35px rgba(245, 158, 11, 0.5), inset 0 0 30px rgba(245, 158, 11, 0.2)';
        }
        default: {
          return '0 0 20px rgba(100, 116, 139, 0.3)';
        }
      }
    }};
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
      box-shadow:
        0 0 30px rgba(59, 130, 246, 0.4),
        inset 0 0 20px rgba(59, 130, 246, 0.1);
    }
    50% {
      opacity: 0.9;
      box-shadow:
        0 0 50px rgba(59, 130, 246, 0.6),
        inset 0 0 30px rgba(59, 130, 246, 0.2);
    }
  }

  @keyframes pausedPulse {
    0%,
    100% {
      opacity: 1;
      box-shadow:
        0 0 25px rgba(245, 158, 11, 0.35),
        inset 0 0 20px rgba(245, 158, 11, 0.1);
    }
    50% {
      opacity: 0.85;
      box-shadow:
        0 0 40px rgba(245, 158, 11, 0.5),
        inset 0 0 30px rgba(245, 158, 11, 0.2);
    }
  }
`;

const NodeIcon = styled.div.withConfig({
  shouldForwardProp: (prop) => !['status', 'kind', 'templateType'].includes(prop),
})<{ status?: string; kind?: string; templateType?: string }>`
  font-size: 20px;
  margin-bottom: 6px;
  color: ${({ status, templateType }) => {
    // Template-specific icon colors for static nodes
    if (status === 'static' && templateType) {
      switch (templateType) {
        case 'Identity': {
          return '#22d3ee'; // cyan-400
        }
        case 'Merge': {
          return '#c084fc'; // purple-400
        }
        case 'Collect': {
          return '#fbbf24'; // amber-400
        }
        default: {
          return '#94a3b8';
        }
      }
    }
    switch (status) {
      case 'completed': {
        return '#10b981';
      }
      case 'running': {
        return '#60a5fa';
      }
      case 'failed': {
        return '#f87171';
      }
      case 'cancelled':
      case 'paused': {
        return '#fbbf24';
      }
      case 'pending': {
        return '#9ca3af';
      }
      case 'waiting': {
        return '#64748b';
      }
      case 'static': {
        return '#94a3b8';
      }
      default: {
        return '#94a3b8';
      }
    }
  }};
  filter: ${({ status }) => {
    switch (status) {
      case 'running': {
        return 'drop-shadow(0 0 4px rgba(96, 165, 250, 0.8))';
      }
      case 'completed': {
        return 'drop-shadow(0 0 4px rgba(16, 185, 129, 0.6))';
      }
      case 'failed': {
        return 'drop-shadow(0 0 4px rgba(248, 113, 113, 0.6))';
      }
      case 'paused': {
        return 'drop-shadow(0 0 4px rgba(251, 191, 36, 0.6))';
      }
      default: {
        return 'none';
      }
    }
  }};
`;

const NodeLabel = styled.div.withConfig({
  shouldForwardProp: (prop) => prop !== 'status',
})<{ status?: string }>`
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  color: ${({ status }) => {
    switch (status) {
      case 'completed': {
        return '#86efac';
      }
      case 'running': {
        return '#93bbfc';
      }
      case 'failed': {
        return '#fca5a5';
      }
      case 'cancelled':
      case 'paused': {
        return '#fcd34d';
      }
      case 'pending': {
        return '#d1d5db';
      }
      case 'waiting': {
        return '#9ca3af';
      }
      case 'static': {
        return '#e2e8f0';
      }
      default: {
        return '#e2e8f0';
      }
    }
  }};
  word-wrap: break-word;
  max-width: 100%;
  line-height: 1.3;
  letter-spacing: 0.025em;
  text-shadow: ${({ status }) => {
    switch (status) {
      case 'running': {
        return '0 0 8px rgba(96, 165, 250, 0.5)';
      }
      case 'completed': {
        return '0 0 8px rgba(16, 185, 129, 0.4)';
      }
      case 'failed': {
        return '0 0 8px rgba(248, 113, 113, 0.4)';
      }
      case 'paused': {
        return '0 0 8px rgba(251, 191, 36, 0.4)';
      }
      default: {
        return 'none';
      }
    }
  }};
`;

// Positioned absolutely at bottom-right so it doesn't consume vertical
// space in the flex layout, leaving more room for the label text.
const NodeKind = styled.div.withConfig({
  shouldForwardProp: (prop) => prop !== 'kind',
})<{ kind?: string }>`
  position: absolute;
  top: 4px;
  right: 6px;
  font-size: 7px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 1px 5px;
  border-radius: 4px;
  border: none;
  opacity: 0.6;
  background: ${({ kind }) => {
    switch (kind) {
      case 'task': {
        return 'rgba(59, 130, 246, 0.15)';
      }
      case 'transformation': {
        return 'rgba(16, 185, 129, 0.15)';
      }
      case 'foreach': {
        return 'rgba(251, 146, 60, 0.15)';
      }
      default: {
        return 'rgba(100, 116, 139, 0.15)';
      }
    }
  }};
  color: ${({ kind }) => {
    switch (kind) {
      case 'task': {
        return '#93bbfc';
      }
      case 'transformation': {
        return '#86efac';
      }
      case 'foreach': {
        return '#fdba74';
      }
      default: {
        return '#cbd5e1';
      }
    }
  }};
`;

// Portal-based tooltip that renders outside the SVG to avoid foreignObject clipping
const NodeTooltipPortal: React.FC<{
  visible: boolean;
  x: number;
  y: number;
  title: string;
  description?: string;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}> = ({ visible, x, y, title, description, onMouseEnter, onMouseLeave }) => {
  if (!visible) return null;
  return ReactDOM.createPortal(
    <div
      style={{
        position: 'fixed',
        left: x,
        top: y - 10,
        transform: 'translate(-50%, -100%)',
        zIndex: 10000,
        pointerEvents: 'auto',
        minWidth: 220,
        maxWidth: 340,
        padding: '12px 16px',
        borderRadius: 10,
        background: 'rgba(10, 15, 30, 0.97)',
        border: '1px solid rgba(148, 163, 184, 0.35)',
        backdropFilter: 'blur(12px)',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255,255,255,0.05)',
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif",
      }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div
        style={{
          fontSize: 12,
          fontWeight: 700,
          color: '#f1f5f9',
          marginBottom: description ? 6 : 0,
          lineHeight: 1.3,
        }}
      >
        {title}
      </div>
      {description && (
        <div
          style={{
            fontSize: 11,
            fontWeight: 400,
            color: '#cbd5e1',
            lineHeight: 1.5,
            maxHeight: 120,
            overflowY: 'auto',
          }}
        >
          {description}
        </div>
      )}
      <div
        style={{
          position: 'absolute',
          top: '100%',
          left: '50%',
          transform: 'translateX(-50%)',
          border: '6px solid transparent',
          borderTopColor: 'rgba(15, 23, 42, 0.95)',
        }}
      />
    </div>,
    document.body
  );
};

// Helper function to get tooltip text for template nodes
const getTemplateTooltip = (templateType?: string): string => {
  if (!templateType) return '';

  switch (templateType) {
    case 'Identity': {
      return 'Identity: Passes data through unchanged (supports high fan-out)';
    }
    case 'Merge': {
      return 'Merge: Combines multiple inputs into a single output';
    }
    case 'Collect': {
      return 'Collect: Gathers all inputs into an array';
    }
    default: {
      return `Template: ${templateType}`;
    }
  }
};

const getStatusIcon = (status?: string, kind?: string, nodeData?: any) => {
  // For template nodes, ALWAYS show their functional icon (even during execution)
  if (kind === 'transformation' && nodeData?.node_template_id) {
    const nodeName = nodeData.name?.toLowerCase() || '';

    if (nodeName.includes('collect')) {
      return <InboxStackIcon className="w-5 h-5" />;
    }
    if (nodeName.includes('merge')) {
      return <ArrowsPointingInIcon className="w-5 h-5" />;
    }
    if (nodeName.includes('identity')) {
      return <ArrowRightIcon className="w-5 h-5" />;
    }

    // Fall back to code bracket for unknown template types
    return <CodeBracketIcon className="w-5 h-5" />;
  }

  // For static nodes, show kind-based icons
  if (status === 'static') {
    switch (kind) {
      case 'task': {
        return <CubeTransparentIcon className="w-5 h-5" />;
      }
      case 'transformation': {
        return <CodeBracketIcon className="w-5 h-5" />;
      }
      case 'foreach': {
        return <ArrowsRightLeftIcon className="w-5 h-5" />;
      }
      default: {
        return <CubeTransparentIcon className="w-5 h-5" />;
      }
    }
  }

  // For execution nodes (non-template), show status-based icons
  switch (status) {
    case 'completed': {
      return <CheckCircleIcon className="w-5 h-5" />;
    }
    case 'running': {
      return <ArrowPathIcon className="w-5 h-5 animate-spin" />;
    }
    case 'failed': {
      return <XCircleIcon className="w-5 h-5" />;
    }
    case 'cancelled':
    case 'paused': {
      return <PauseCircleIcon className="w-5 h-5" />;
    }
    case 'pending': {
      return <ClockIcon className="w-5 h-5" />;
    }
    case 'waiting': {
      return <ClockIcon className="w-5 h-5" />;
    }
    default: {
      return <PlayCircleIcon className="w-5 h-5" />;
    }
  }
};

// Determine text sizing tier based on label length and node dimensions.
// Returns 'normal' | 'shrink' | 'shrink-expand' so the renderer can
// adjust font-size accordingly. The data layer uses the companion
// `getNodeHeight` to match box dimensions.
//
// Layout budget inside a node (at base height):
//   padding: 12px*2 = 24px, icon+margin: 26px, border: 4px
//   (badge is absolutely positioned, doesn't consume flow space)
//   fixed overhead ≈ 54px → available text height = baseHeight - 54
//
// At 12px font (line-height 1.3) each line is ~16px, at 10px each line is ~13px.
function getTextTier(text: string, nodeWidth: number): 'normal' | 'shrink' | 'shrink-expand' {
  const usableWidth = nodeWidth - 28; // padding (24) + border (4)
  const normalCharsPerLine = Math.floor(usableWidth / 7); // ~7px/char at 12px
  const shrinkCharsPerLine = Math.floor(usableWidth / 6); // ~6px/char at 10px

  const normalLines = Math.ceil(text.length / normalCharsPerLine);
  const shrinkLines = Math.ceil(text.length / shrinkCharsPerLine);

  if (normalLines <= 2) return 'normal';
  if (shrinkLines <= 3) return 'shrink';
  return 'shrink-expand';
}

// Compute node height for the data layer. Call with the same base dimensions
// (e.g. 180x100 for View, 220x120 for Run) and the node label text.
export function getNodeHeight(text: string, baseWidth: number, baseHeight: number): number {
  const tier = getTextTier(text, baseWidth);
  if (tier === 'shrink-expand') return Math.round(baseHeight * 1.2);
  return baseHeight;
}

const WorkflowNode: React.FC<NodeProps & { isSelected?: boolean }> = (nodeProps) => {
  const ref = React.useRef<SVGForeignObjectElement | null>(null);
  const [tooltip, setTooltip] = useState<{
    visible: boolean;
    x: number;
    y: number;
    title: string;
    description?: string;
  }>({ visible: false, x: 0, y: 0, title: '' });
  const showTimeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideTimeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  // Store tooltip content in refs so the SVG event listeners always read current values
  const tooltipDataRef = React.useRef<{ title: string; description?: string } | null>(null);
  // Track selection state in a ref so the SVG hover listener can read it without re-binding
  const isSelectedRef = React.useRef(nodeProps.isSelected ?? false);
  React.useEffect(() => {
    isSelectedRef.current = nodeProps.isSelected ?? false;
  }, [nodeProps.isSelected]);

  const dismissTooltip = useCallback(() => {
    setTooltip((prev) => ({ ...prev, visible: false }));
  }, []);

  const hideTooltip = useCallback(() => {
    if (showTimeoutRef.current) {
      clearTimeout(showTimeoutRef.current);
      showTimeoutRef.current = null;
    }
    hideTimeoutRef.current = setTimeout(dismissTooltip, 150);
  }, [dismissTooltip]);

  const cancelHide = useCallback(() => {
    if (hideTimeoutRef.current) {
      clearTimeout(hideTimeoutRef.current);
      hideTimeoutRef.current = null;
    }
  }, []);

  // Attach hover listeners to the parent SVG <g> element so clicks pass
  // through to Reaflow's native handlers (selection, details panel, etc.)
  React.useEffect(() => {
    const fo = ref.current;
    const g = fo?.parentElement; // the SVG <g> that Reaflow renders
    if (!g) return;

    const onEnter = () => {
      // Don't show tooltip when this node is selected (details panel is open)
      if (isSelectedRef.current) return;
      if (hideTimeoutRef.current) {
        clearTimeout(hideTimeoutRef.current);
        hideTimeoutRef.current = null;
      }
      if (showTimeoutRef.current) {
        clearTimeout(showTimeoutRef.current);
      }
      const data = tooltipDataRef.current;
      if (!data) return;
      const rect = g.getBoundingClientRect();
      const pos = { x: rect.left + rect.width / 2, y: rect.top };
      showTimeoutRef.current = setTimeout(() => {
        setTooltip({ visible: true, ...pos, title: data.title, description: data.description });
      }, 1000);
    };

    const onLeave = () => {
      if (showTimeoutRef.current) {
        clearTimeout(showTimeoutRef.current);
        showTimeoutRef.current = null;
      }
      hideTimeoutRef.current = setTimeout(dismissTooltip, 150);
    };

    const onClick = () => {
      // Hide tooltip immediately on click so it doesn't obstruct details panel
      if (showTimeoutRef.current) {
        clearTimeout(showTimeoutRef.current);
        showTimeoutRef.current = null;
      }
      setTooltip((prev) => ({ ...prev, visible: false }));
    };

    g.addEventListener('mouseenter', onEnter);
    g.addEventListener('mouseleave', onLeave);
    g.addEventListener('click', onClick);
    return () => {
      g.removeEventListener('mouseenter', onEnter);
      g.removeEventListener('mouseleave', onLeave);
      g.removeEventListener('click', onClick);
    };
  }, [dismissTooltip]);

  // Strip custom prop before passing to Reaflow's Node
  const { isSelected, ...reaflowProps } = nodeProps;

  return (
    <Node
      {...reaflowProps}
      label={<React.Fragment />}
      style={
        // Hide the rectangle for template nodes
        reaflowProps.properties?.data?.nodeData?.node_template_id
          ? { fill: 'transparent', stroke: 'transparent', strokeWidth: 0 }
          : undefined
      }
    >
      {(props: NodeChildProps) => {
        const status = props.node.data?.status || 'static';
        const kind = props.node.data?.kind || 'task';
        const nodeData = props.node.data?.nodeData;
        const isStatic = status === 'static';

        // Extract template type for transformation nodes
        let templateType: string | undefined;
        if (kind === 'transformation' && nodeData?.node_template_id) {
          // Determine template type from node name
          const nodeName = nodeData.name?.toLowerCase() || '';
          if (nodeName.includes('collect')) {
            templateType = 'Collect';
          } else if (nodeName.includes('merge')) {
            templateType = 'Merge';
          } else if (nodeName.includes('identity')) {
            templateType = 'Identity';
          }
        }

        // Get tooltip text for template nodes
        const tooltipText = getTemplateTooltip(templateType);

        // Render compact circular nodes for template transformations
        if (templateType) {
          // Update tooltip data ref for the SVG hover listener
          tooltipDataRef.current = tooltipText ? { title: tooltipText } : null;
          return (
            <StyledForeignObject
              width={props.width}
              height={props.height}
              ref={ref}
              status={status}
              kind={kind}
            >
              <NodeContent
                status={status}
                kind={kind}
                isStatic={isStatic}
                isSelected={isSelected}
                templateType={templateType}
                style={{
                  width: '60px',
                  height: '60px',
                  borderRadius: '50%',
                  padding: '0',
                  justifyContent: 'center',
                  alignItems: 'center',
                }}
              >
                <NodeIcon
                  status={status}
                  kind={kind}
                  templateType={templateType}
                  style={{ margin: 0, fontSize: '24px' }}
                >
                  {getStatusIcon(status, kind, nodeData)}
                </NodeIcon>
              </NodeContent>
              <NodeTooltipPortal
                {...tooltip}
                onMouseEnter={cancelHide}
                onMouseLeave={hideTooltip}
              />
            </StyledForeignObject>
          );
        }

        // Regular node rendering
        const labelText = props.node.text || nodeData?.name || 'Unknown Node';
        const tier = getTextTier(labelText, props.width);
        const shrinkFont = tier !== 'normal';
        const taskDescription = props.node.data?.taskDescription as string | undefined;

        // Update tooltip data ref for the SVG hover listener
        tooltipDataRef.current = taskDescription
          ? { title: labelText, description: taskDescription }
          : null;

        return (
          <StyledForeignObject
            width={props.width}
            height={props.height}
            ref={ref}
            status={status}
            kind={kind}
          >
            <NodeContent
              status={status}
              kind={kind}
              isStatic={isStatic}
              isSelected={isSelected}
              templateType={templateType}
              style={{ overflow: 'hidden' }}
            >
              <NodeIcon status={status} kind={kind} templateType={templateType}>
                {getStatusIcon(status, kind, nodeData)}
              </NodeIcon>
              <NodeLabel
                status={status}
                style={
                  shrinkFont
                    ? {
                        fontSize: '10px',
                        display: '-webkit-box',
                        WebkitLineClamp: 4,
                        WebkitBoxOrient: 'vertical' as const,
                        overflow: 'hidden',
                      }
                    : undefined
                }
              >
                {labelText}
              </NodeLabel>
              <NodeKind kind={kind}>{kind}</NodeKind>
            </NodeContent>
            <NodeTooltipPortal {...tooltip} onMouseEnter={cancelHide} onMouseLeave={hideTooltip} />
          </StyledForeignObject>
        );
      }}
    </Node>
  );
};

export default WorkflowNode;
