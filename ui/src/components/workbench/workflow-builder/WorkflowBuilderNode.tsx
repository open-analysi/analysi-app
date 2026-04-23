/**
 * WorkflowBuilderNode - Custom node component for the workflow builder
 *
 * Renders different node styles based on type (task, transformation, foreach)
 */
import React from 'react';

import {
  CubeTransparentIcon,
  CodeBracketIcon,
  ArrowPathIcon,
  ArrowRightIcon,
  ArrowsPointingInIcon,
  RectangleStackIcon,
} from '@heroicons/react/24/outline';
import { Node, NodeProps, Port } from 'reaflow';

interface WorkflowBuilderNodeProps extends NodeProps {
  isSelected?: boolean;
}

/**
 * Get icon for node based on kind and template
 */
// eslint-disable-next-line sonarjs/function-return-type -- returns different JSX icons based on kind
function getNodeIcon(kind: string, templateId?: string): React.ReactNode {
  const iconClass = 'h-5 w-5';

  if (kind === 'task') {
    return <CubeTransparentIcon className={iconClass} />;
  }

  if (kind === 'foreach') {
    return <ArrowPathIcon className={iconClass} />;
  }

  // Transformation icons based on template
  if (kind === 'transformation') {
    switch (templateId) {
      case 'identity':
        return <ArrowRightIcon className={iconClass} />;
      case 'merge':
        return <ArrowsPointingInIcon className={iconClass} />;
      case 'collect':
        return <RectangleStackIcon className={iconClass} />;
      default:
        return <CodeBracketIcon className={iconClass} />;
    }
  }

  return <CodeBracketIcon className={iconClass} />;
}

/**
 * Get node colors based on kind
 */
function getNodeColors(
  kind: string,
  isSelected: boolean
): { bg: string; border: string; text: string } {
  const baseColors = {
    task: {
      bg: 'rgba(59, 130, 246, 0.15)',
      border: isSelected ? '#f472b6' : '#3b82f6',
      text: '#93c5fd',
    },
    transformation: {
      bg: 'rgba(16, 185, 129, 0.15)',
      border: isSelected ? '#f472b6' : '#10b981',
      text: '#6ee7b7',
    },
    foreach: {
      bg: 'rgba(249, 115, 22, 0.15)',
      border: isSelected ? '#f472b6' : '#f97316',
      text: '#fdba74',
    },
  };

  return baseColors[kind as keyof typeof baseColors] || baseColors.task;
}

const WorkflowBuilderNode: React.FC<WorkflowBuilderNodeProps> = (props) => {
  const { properties, isSelected = false } = props;

  const data = (properties?.data || {}) as Record<string, unknown>;

  const kind = (data.kind || 'task') as string;

  const templateId = data.nodeTemplateId as string | undefined;

  const isTemplateNode = kind === 'transformation' && templateId;
  const colors = getNodeColors(kind, isSelected);

  return (
    <Node
      {...props}
      style={{
        fill: colors.bg,
        stroke: colors.border,
        strokeWidth: isSelected ? 3 : 2,
        rx: isTemplateNode ? 30 : 12,
        ry: isTemplateNode ? 30 : 12,
      }}
      port={
        <Port
          style={{
            fill: 'rgba(182, 133, 255, 0.8)',
            stroke: '#b685ff',
            strokeWidth: 1,
          }}
          rx={5}
          ry={5}
        />
      }
    >
      {(nodeProps) => {
        const { width, height } = nodeProps as { width: number; height: number };

        const nodeText = (properties?.text || 'Node') as string;

        return (
          <foreignObject
            width={width}
            height={height}
            style={{ overflow: 'visible', pointerEvents: 'none' }}
          >
            <div
              style={{
                width: '100%',
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: isTemplateNode ? '8px' : '12px',
                color: colors.text,
                fontFamily: 'system-ui, -apple-system, sans-serif',
                pointerEvents: 'none',
              }}
            >
              {/* Icon */}
              <div
                style={{
                  marginBottom: isTemplateNode ? '0' : '8px',
                  opacity: 0.8,
                }}
              >
                {getNodeIcon(kind, templateId)}
              </div>

              {/* Node name (only for non-template nodes) */}
              {!isTemplateNode && (
                <div
                  style={{
                    fontSize: '13px',
                    fontWeight: 500,
                    textAlign: 'center',
                    lineHeight: 1.3,
                    maxWidth: '100%',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                  }}
                >
                  {nodeText}
                </div>
              )}

              {/* Kind badge (for non-template nodes) */}
              {!isTemplateNode && (
                <div
                  style={{
                    marginTop: '6px',
                    fontSize: '10px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                    opacity: 0.6,
                  }}
                >
                  {kind}
                </div>
              )}

              {/* Template name for transformation nodes */}
              {isTemplateNode && (
                <div
                  style={{
                    marginTop: '4px',
                    fontSize: '10px',
                    textTransform: 'capitalize',
                    fontWeight: 500,
                  }}
                >
                  {templateId}
                </div>
              )}
            </div>
          </foreignObject>
        );
      }}
    </Node>
  );
};

export default WorkflowBuilderNode;
