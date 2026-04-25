/**
 * WorkflowBuilderPalette - Component palette for workflow builder
 *
 * Structure-first approach: Click to add nodes to canvas.
 * ELK handles positioning automatically.
 */
/* eslint-disable sonarjs/no-nested-conditional */
import React, { useEffect, useState } from 'react';

import {
  CubeTransparentIcon,
  CodeBracketIcon,
  ArrowPathIcon,
  ArrowRightIcon,
  ArrowsPointingInIcon,
  RectangleStackIcon,
  MagnifyingGlassIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';

import { backendApi } from '../../../services/backendApi';
import type { Task } from '../../../types/knowledge';
import {
  TRANSFORMATION_TEMPLATES,
  FOREACH_TEMPLATE,
  type NodeTemplate,
} from '../../../types/workflowBuilder';

interface WorkflowBuilderPaletteProps {
  onClick: (template: NodeTemplate) => void;
}

/**
 * Get icon for node template
 */
// eslint-disable-next-line sonarjs/function-return-type -- returns different JSX icons based on kind
function getTemplateIcon(template: NodeTemplate): React.ReactNode {
  const iconClass = 'h-4 w-4';

  if (template.kind === 'task') {
    return <CubeTransparentIcon className={iconClass} />;
  }

  if (template.kind === 'foreach') {
    return <ArrowPathIcon className={iconClass} />;
  }

  // Transformation icons based on template ID
  switch (template.templateId) {
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

/**
 * Get border color for node kind
 */
function getBorderColor(kind: NodeTemplate['kind']): string {
  switch (kind) {
    case 'task':
      return 'hover:border-blue-500 active:border-blue-400';
    case 'transformation':
      return 'hover:border-green-500 active:border-green-400';
    case 'foreach':
      return 'hover:border-orange-500 active:border-orange-400';
    default:
      return 'hover:border-gray-500';
  }
}

/**
 * Collapsible section component
 */
const PaletteSection: React.FC<{
  title: string;
  children: React.ReactNode;
  defaultExpanded?: boolean;
}> = ({ title, children, defaultExpanded = true }) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  return (
    <div className="mb-4">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center space-x-1 text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 hover:text-gray-300 w-full"
      >
        {isExpanded ? (
          <ChevronDownIcon className="h-3 w-3" />
        ) : (
          <ChevronRightIcon className="h-3 w-3" />
        )}
        <span>{title}</span>
      </button>
      {isExpanded && <div className="space-y-1">{children}</div>}
    </div>
  );
};

/**
 * Clickable palette item - click to add to canvas
 */
const PaletteItem: React.FC<{
  template: NodeTemplate;
  onClick: (template: NodeTemplate) => void;
}> = ({ template, onClick }) => {
  const [isClicked, setIsClicked] = useState(false);

  const handleClick = () => {
    setIsClicked(true);
    onClick(template);
    // Reset animation after a short delay
    setTimeout(() => setIsClicked(false), 200);
  };

  return (
    <button
      onClick={handleClick}
      className={`
        w-full p-2 bg-dark-700 rounded border border-gray-600
        text-sm text-gray-300 cursor-pointer
        hover:bg-dark-600 active:bg-dark-500 transition-all duration-150
        flex items-center space-x-2 group
        ${getBorderColor(template.kind)}
        ${isClicked ? 'scale-95' : ''}
      `}
      title={`${template.description || template.name} - Click to add`}
    >
      <span className="text-gray-400 group-hover:text-gray-300">{getTemplateIcon(template)}</span>
      <span className="truncate flex-1 text-left">{template.name}</span>
      <PlusIcon className="h-3 w-3 text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity" />
    </button>
  );
};

export const WorkflowBuilderPalette: React.FC<WorkflowBuilderPaletteProps> = ({ onClick }) => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  // Fetch tasks on mount
  useEffect(() => {
    const fetchTasks = async () => {
      try {
        setIsLoading(true);

        const response = await backendApi.getTasks({ limit: 100 });

        setTasks(response.tasks);
      } catch (err) {
        console.error('Failed to fetch tasks:', err);
      } finally {
        setIsLoading(false);
      }
    };

    void fetchTasks();
  }, []);

  // Convert tasks to node templates
  const taskTemplates: NodeTemplate[] = tasks
    .filter((task) =>
      searchTerm
        ? task.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          task.description?.toLowerCase().includes(searchTerm.toLowerCase())
        : true
    )
    .map((task) => ({
      id: `task-${task.id}`,
      name: task.name,
      kind: 'task' as const,
      description: task.description ?? undefined,
      taskId: task.id,
      taskName: task.name,
    }));

  // Filter transformation templates
  const filteredTransformations = TRANSFORMATION_TEMPLATES.filter((t) =>
    searchTerm
      ? t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        t.description?.toLowerCase().includes(searchTerm.toLowerCase())
      : true
  );

  // Filter foreach template
  const showForEach =
    !searchTerm ||
    FOREACH_TEMPLATE.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    FOREACH_TEMPLATE.description?.toLowerCase().includes(searchTerm.toLowerCase());

  return (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="p-2 border-b border-gray-700">
        <div className="relative">
          <MagnifyingGlassIcon className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search components..."
            className="w-full pl-8 pr-3 py-1.5 text-sm bg-dark-700 border border-gray-600 rounded-sm text-white placeholder-gray-500 focus:outline-hidden focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {/* Hint text */}
      <div className="px-3 py-2 text-xs text-gray-500 border-b border-gray-700">
        Click to add. Click + to connect. Select to delete.
      </div>

      {/* Scrollable content */}
      <div className="flex-1 min-h-0 overflow-y-auto p-3">
        {/* Tasks Section */}
        <PaletteSection title="Tasks">
          {isLoading ? (
            <div className="text-center py-4">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary mx-auto"></div>
              <p className="text-xs text-gray-500 mt-2">Loading tasks...</p>
            </div>
          ) : taskTemplates.length === 0 ? (
            <p className="text-xs text-gray-500 py-2">
              {searchTerm ? 'No tasks match your search' : 'No tasks available'}
            </p>
          ) : (
            taskTemplates.map((template) => (
              <PaletteItem key={template.id} template={template} onClick={onClick} />
            ))
          )}
        </PaletteSection>

        {/* Transformations Section */}
        <PaletteSection title="Transformations">
          {filteredTransformations.length === 0 ? (
            <p className="text-xs text-gray-500 py-2">No transformations match your search</p>
          ) : (
            filteredTransformations.map((template) => (
              <PaletteItem key={template.id} template={template} onClick={onClick} />
            ))
          )}
        </PaletteSection>

        {/* Control Flow Section */}
        <PaletteSection title="Control Flow">
          {showForEach ? (
            <PaletteItem template={FOREACH_TEMPLATE} onClick={onClick} />
          ) : (
            <p className="text-xs text-gray-500 py-2">No control flow nodes match your search</p>
          )}
        </PaletteSection>
      </div>
    </div>
  );
};

export default WorkflowBuilderPalette;
