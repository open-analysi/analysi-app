import React from 'react';

import { SparklesIcon } from '@heroicons/react/24/outline';
import Markdown from 'react-markdown';

import { reportMarkdownComponents } from '../alerts/markdownComponents';

/** Compact markdown overrides sized for the narrow chat panel. */
const chatMarkdownComponents = {
  ...reportMarkdownComponents,
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="text-sm font-bold mb-2 text-cyan-400">{children}</h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="text-sm font-semibold mb-1.5 text-emerald-400">{children}</h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="text-sm font-medium mb-1 text-violet-400">{children}</h3>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="mb-2 text-gray-200 text-sm leading-relaxed">{children}</p>
  ),
};

/** Map tool function names to user-friendly labels. */
const TOOL_LABELS: Record<string, string> = {
  get_alert: 'Looking up alert',
  search_alerts: 'Searching alerts',
  get_workflow: 'Looking up workflow',
  list_workflows: 'Listing workflows',
  get_task: 'Looking up task',
  list_tasks: 'Listing tasks',
  get_integration_health: 'Checking integration',
  list_integrations: 'Listing integrations',
  get_workflow_run: 'Looking up workflow run',
  get_task_run: 'Looking up task run',
  search_audit_trail: 'Searching audit trail',
  load_product_skill: 'Loading knowledge',
  search_tenant_knowledge: 'Searching knowledge',
  read_knowledge_document: 'Reading document',
  read_knowledge_table: 'Reading table',
  run_workflow: 'Running workflow',
  run_task: 'Running task',
  analyze_alert: 'Analyzing alert',
  create_alert: 'Creating alert',
};

interface Props {
  text: string;
  activeTool?: string | null;
}

/**
 * Renders the assistant's in-progress streaming response with a blinking cursor.
 * Shows tool execution status when the agent is calling tools.
 * Markdown is rendered live as chunks arrive.
 */
export const StreamingMessage: React.FC<Props> = ({ text, activeTool }) => {
  const toolLabel = activeTool ? (TOOL_LABELS[activeTool] ?? `Using ${activeTool}`) : null;

  return (
    <div className="flex gap-3 px-4 py-3 bg-dark-800/50">
      {/* Avatar */}
      <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-primary/20 text-primary">
        <SparklesIcon className="w-4 h-4" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-gray-400 mb-1">Analysi</p>
        <div className="prose-chat text-sm break-words">
          {text && <Markdown components={chatMarkdownComponents}>{text}</Markdown>}
          {toolLabel && (
            <div className="flex items-center gap-2 text-xs text-gray-400 py-1">
              <div className="w-3 h-3 border border-primary/40 border-t-primary rounded-full animate-spin" />
              <span>{toolLabel}...</span>
            </div>
          )}
          {!toolLabel && (
            <span className="inline-block w-2 h-4 bg-primary/60 animate-pulse ml-0.5 align-text-bottom" />
          )}
        </div>
      </div>
    </div>
  );
};
