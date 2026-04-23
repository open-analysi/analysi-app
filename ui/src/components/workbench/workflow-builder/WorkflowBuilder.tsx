/**
 * WorkflowBuilder - Interactive workflow editor component
 *
 * Used in two contexts:
 * 1. Workbench tab - Create new workflows from scratch
 * 2. Workflows detail page - Edit existing workflows
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';

import {
  PlusIcon,
  ArrowUturnLeftIcon,
  ArrowUturnRightIcon,
  Bars3Icon,
  XMarkIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline';
import {
  Panel,
  Group,
  Separator,
  useDefaultLayout,
  type PanelImperativeHandle,
} from 'react-resizable-panels';

import { useWorkflowBuilderStore } from '../../../store/workflowBuilderStore';
import type { Workflow } from '../../../types/workflow';
import type { NodeTemplate } from '../../../types/workflowBuilder';
import { ConfirmDialog } from '../../common/ConfirmDialog';

import { WorkflowBuilderCanvas } from './WorkflowBuilderCanvas';
import { WorkflowBuilderPalette } from './WorkflowBuilderPalette';
import { WorkflowBuilderProperties } from './WorkflowBuilderProperties';

/**
 * Types for pending confirmation dialogs
 */
type PendingConfirmation =
  | { type: 'restore-existing'; workflow: Workflow }
  | { type: 'restore-new' }
  | { type: 'discard-close' }
  | { type: 'discard-new' }
  | null;

/**
 * Generate a unique ID for canvas elements
 */
function generateId(prefix: string): string {
  const randomPart =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID().slice(0, 8)
      : // eslint-disable-next-line sonarjs/pseudo-random -- fallback for environments without crypto
        Date.now().toString(36) + Math.random().toString(36).substring(2, 9);
  return `${prefix}-${randomPart}`;
}

export interface WorkflowBuilderProps {
  // Mode: new or edit existing
  workflowId?: string;
  workflow?: Workflow;

  // Callbacks
  onSave?: (workflow: Workflow) => void;
  onClose?: () => void;

  // UI options
  showHeader?: boolean;
  className?: string;
}

export const WorkflowBuilder: React.FC<WorkflowBuilderProps> = ({
  workflowId,
  workflow,
  onSave,
  onClose,
  showHeader = true,
  className = '',
}) => {
  const store = useWorkflowBuilderStore();
  const palettePanelRef = useRef<PanelImperativeHandle>(null);
  const propertiesPanelRef = useRef<PanelImperativeHandle>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation>(null);

  // Persistent layouts for resizable panels (v4 API)
  const { defaultLayout: mainLayout, onLayoutChanged: onMainLayoutChanged } = useDefaultLayout({
    id: 'workflow-builder-main',
  });
  const { defaultLayout: canvasLayout, onLayoutChanged: onCanvasLayoutChanged } =
    useDefaultLayout({ id: 'workflow-builder-canvas' });

  const isEditMode = !!(workflowId || workflow);

  // Load workflow on mount if editing
  // Also checks for persisted drafts and prompts to restore
  useEffect(() => {
    if (workflow) {
      // Check if there's a persisted draft for this workflow
      // The store persists to localStorage, so we need to check if the current
      // store state differs from the workflow being loaded
      const hasPersistedDraft =
        store.workflowId === workflow.id &&
        store.isDirty &&
        (store.nodes.length > 0 || store.workflowName !== workflow.name);

      if (hasPersistedDraft) {
        // Ask user if they want to restore their draft
        setPendingConfirmation({ type: 'restore-existing', workflow });
      } else {
        // No draft or draft matches server - load the workflow
        store.loadWorkflow(workflow);
      }
    } else if (!workflowId) {
      // New workflow mode - check for persisted new workflow draft
      const hasNewWorkflowDraft = !store.workflowId && store.isDirty && store.nodes.length > 0;

      if (hasNewWorkflowDraft) {
        setPendingConfirmation({ type: 'restore-new' });
      } else {
        store.newWorkflow();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflow, workflowId]);

  // Handle confirmation dialog responses
  const handleConfirm = useCallback(() => {
    if (!pendingConfirmation) return;

    switch (pendingConfirmation.type) {
      case 'restore-existing':
        // User wants to restore draft - keep current store state
        break;
      case 'restore-new':
        // User wants to restore draft - keep current store state
        break;
      case 'discard-close':
        // User confirmed discarding changes
        store.reset();
        onClose?.();
        break;
      case 'discard-new':
        // User confirmed starting new workflow
        store.newWorkflow();
        break;
    }
    setPendingConfirmation(null);
  }, [pendingConfirmation, store, onClose]);

  const handleCancel = useCallback(() => {
    if (!pendingConfirmation) return;

    switch (pendingConfirmation.type) {
      case 'restore-existing':
        // User declined restore - load the saved workflow
        store.loadWorkflow(pendingConfirmation.workflow);
        break;
      case 'restore-new':
        // User declined restore - start fresh
        store.newWorkflow();
        break;
      case 'discard-close':
        // User cancelled - stay on page
        break;
      case 'discard-new':
        // User cancelled - stay on current workflow
        break;
    }
    setPendingConfirmation(null);
  }, [pendingConfirmation, store]);

  // Get dialog config based on pending confirmation type
  const getDialogConfig = () => {
    const timestamp = store.draftTimestamp
      ? new Date(store.draftTimestamp).toLocaleString()
      : 'a previous session';

    switch (pendingConfirmation?.type) {
      case 'restore-existing':
        return {
          title: 'Restore Unsaved Draft?',
          message: `Found an unsaved draft from ${timestamp}. Would you like to restore your previous work or use the saved version?`,
          confirmLabel: 'Restore Draft',
          cancelLabel: 'Use Saved',
          variant: 'question' as const,
        };
      case 'restore-new':
        return {
          title: 'Restore Unsaved Draft?',
          message: `Found an unsaved draft from ${timestamp}. Would you like to restore your previous work or start fresh?`,
          confirmLabel: 'Restore Draft',
          cancelLabel: 'Start Fresh',
          variant: 'question' as const,
        };
      case 'discard-close':
        return {
          title: 'Discard Unsaved Changes?',
          message:
            'You have unsaved changes. Are you sure you want to exit? All your progress will be lost.',
          confirmLabel: 'Discard & Exit',
          cancelLabel: 'Keep Editing',
          variant: 'warning' as const,
        };
      case 'discard-new':
        return {
          title: 'Discard Current Workflow?',
          message:
            'You have unsaved changes. Are you sure you want to start a new workflow? Your current progress will be lost.',
          confirmLabel: 'Start New',
          cancelLabel: 'Keep Editing',
          variant: 'warning' as const,
        };
      default:
        return {
          title: '',
          message: '',
          confirmLabel: 'Confirm',
          cancelLabel: 'Cancel',
          variant: 'question' as const,
        };
    }
  };

  // Handle save
  const handleSave = async () => {
    const savedWorkflow = await store.saveWorkflow();
    if (savedWorkflow && onSave) {
      onSave(savedWorkflow);
    }
  };

  // Handle close with unsaved changes check
  const handleClose = () => {
    if (store.isDirty) {
      setPendingConfirmation({ type: 'discard-close' });
    } else {
      store.reset();
      onClose?.();
    }
  };

  // Toggle palette panel
  const togglePalette = () => {
    const panel = palettePanelRef.current;
    if (panel) {
      if (panel.isCollapsed()) {
        panel.expand();
      } else {
        panel.collapse();
      }
    }
  };

  // Toggle properties panel
  const toggleProperties = () => {
    const panel = propertiesPanelRef.current;
    if (panel) {
      if (panel.isCollapsed()) {
        panel.expand();
      } else {
        panel.collapse();
      }
    }
  };

  // Handle adding a node from the palette (click to add)
  const handleAddNode = (template: NodeTemplate) => {
    // Create a new canvas node from the template
    const nodeId = generateId('node');
    const newNode = {
      id: nodeId,
      text: template.name,
      kind: template.kind,
      taskId: template.taskId,
      nodeTemplateId: template.templateId,
      description: template.description,
    };

    store.addNode(newNode);
  };

  return (
    <div className={`flex flex-col h-full bg-dark-900 ${className}`}>
      {/* Toolbar */}
      {showHeader && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 bg-dark-800">
          <div className="flex items-center space-x-4">
            {/* Toggle Palette Button */}
            <button
              onClick={togglePalette}
              className="p-1.5 text-gray-400 hover:text-white hover:bg-dark-700 rounded-sm"
              title="Toggle palette (Ctrl+B)"
            >
              <Bars3Icon className="h-5 w-5" />
            </button>

            {/* Workflow Name */}
            <div className="flex items-center space-x-2">
              <input
                type="text"
                value={store.workflowName}
                onChange={(e) => store.setWorkflowName(e.target.value)}
                className="bg-transparent border-none text-lg font-semibold text-white focus:outline-hidden focus:ring-1 focus:ring-primary rounded-sm px-2 py-1 w-64"
                placeholder="Workflow name..."
              />
              {store.isDirty && (
                <span className="text-xs text-yellow-500" title="Unsaved changes">
                  *
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center space-x-2">
            {/* Undo/Redo */}
            <div className="flex items-center border-r border-gray-600 pr-2 mr-2">
              <button
                onClick={() => store.undo()}
                disabled={!store.canUndo()}
                className="p-1.5 text-gray-400 hover:text-white hover:bg-dark-700 rounded-sm disabled:opacity-30 disabled:cursor-not-allowed"
                title="Undo (Ctrl+Z)"
              >
                <ArrowUturnLeftIcon className="h-4 w-4" />
              </button>
              <button
                onClick={() => store.redo()}
                disabled={!store.canRedo()}
                className="p-1.5 text-gray-400 hover:text-white hover:bg-dark-700 rounded-sm disabled:opacity-30 disabled:cursor-not-allowed"
                title="Redo (Ctrl+Y)"
              >
                <ArrowUturnRightIcon className="h-4 w-4" />
              </button>
            </div>

            {/* Toggle Properties Panel */}
            <button
              onClick={toggleProperties}
              className="p-1.5 text-gray-400 hover:text-white hover:bg-dark-700 rounded-sm border-r border-gray-600 pr-2 mr-2"
              title="Toggle properties panel"
            >
              <Cog6ToothIcon className="h-5 w-5" />
            </button>

            {/* New Workflow */}
            <button
              onClick={() => {
                if (store.isDirty) {
                  setPendingConfirmation({ type: 'discard-new' });
                } else {
                  store.newWorkflow();
                }
              }}
              className="px-3 py-1.5 text-sm text-gray-300 hover:text-white border border-gray-600 rounded-md hover:bg-dark-700 flex items-center space-x-1"
            >
              <PlusIcon className="h-4 w-4" />
              <span>New</span>
            </button>

            {/* Close Button (when editing) */}
            {onClose && (
              <button
                onClick={handleClose}
                className="px-3 py-1.5 text-sm text-gray-300 hover:text-white border border-gray-600 rounded-md hover:bg-dark-700 flex items-center space-x-1"
              >
                <XMarkIcon className="h-4 w-4" />
                <span>Cancel</span>
              </button>
            )}

            {/* Save Button */}
            <button
              onClick={() => void handleSave()}
              disabled={store.isSaving || (!store.isDirty && isEditMode)}
              className="px-3 py-1.5 text-sm text-white bg-primary rounded-md hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-1"
            >
              {store.isSaving ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  <span>Saving...</span>
                </>
              ) : (
                <span>{isEditMode ? 'Save Changes' : 'Save Workflow'}</span>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Main Content with Panels */}
      <div className="flex-1 min-h-0">
        <Group
          orientation="horizontal"
          defaultLayout={mainLayout}
          onLayoutChanged={onMainLayoutChanged}
        >
          {/* Palette Panel */}
          <Panel
            panelRef={palettePanelRef}
            defaultSize="18"
            minSize="5"
            maxSize="30"
            collapsible
            collapsedSize="0"
            id="palette"
          >
            <div className="h-full bg-dark-800 border-r border-gray-700 flex flex-col overflow-hidden">
              <div className="shrink-0 px-3 py-2 bg-dark-700 border-b border-gray-600 flex items-center justify-between">
                <h3 className="text-sm font-medium text-white">Components</h3>
                <button
                  onClick={togglePalette}
                  className="p-1 text-gray-400 hover:text-white"
                  title="Collapse palette"
                >
                  <ChevronLeftIcon className="h-4 w-4" />
                </button>
              </div>
              <div className="flex-1 min-h-0 overflow-hidden">
                <WorkflowBuilderPalette onClick={handleAddNode} />
              </div>
            </div>
          </Panel>

          <Separator className="w-1 bg-gray-700 hover:bg-blue-500 transition-colors cursor-col-resize" />

          {/* Canvas Area */}
          <Panel minSize="40">
            <Group
              orientation="horizontal"
              defaultLayout={canvasLayout}
              onLayoutChanged={onCanvasLayoutChanged}
            >
              {/* Main Canvas */}
              <Panel minSize="50">
                <WorkflowBuilderCanvas />
              </Panel>

              <Separator className="w-1 bg-gray-700 hover:bg-blue-500 transition-colors cursor-col-resize" />

              {/* Properties Panel */}
              <Panel
                panelRef={propertiesPanelRef}
                defaultSize="25"
                minSize="15"
                maxSize="40"
                collapsible
                collapsedSize="0"
                id="properties"
              >
                <div className="h-full bg-dark-800 border-l border-gray-700 flex flex-col">
                  <div className="px-3 py-2 bg-dark-700 border-b border-gray-600 flex items-center justify-between">
                    <h3 className="text-sm font-medium text-white">Properties</h3>
                    <button
                      onClick={toggleProperties}
                      className="p-1 text-gray-400 hover:text-white"
                      title="Collapse properties"
                    >
                      <ChevronRightIcon className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="flex-1 overflow-y-auto">
                    <WorkflowBuilderProperties />
                  </div>
                </div>
              </Panel>
            </Group>
          </Panel>
        </Group>
      </div>

      {/* Error Display */}
      {store.error && (
        <div className="px-4 py-2 bg-red-900/50 border-t border-red-700 text-red-300 text-sm">
          {store.error}
        </div>
      )}

      {/* Confirmation Dialog */}
      <ConfirmDialog
        isOpen={pendingConfirmation !== null}
        onClose={handleCancel}
        onConfirm={handleConfirm}
        {...getDialogConfig()}
      />
    </div>
  );
};

export default WorkflowBuilder;
