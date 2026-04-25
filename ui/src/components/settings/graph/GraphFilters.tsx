import React from 'react';

import { getNodeConfig, getEdgeConfig } from '../../../types/kdg';

interface GraphFiltersProps {
  onNodeTypeFilterChange: (nodeTypes: string[]) => void;
  onEdgeTypeFilterChange: (edgeTypes: string[]) => void;
  nodeTypes: string[];
  edgeTypes: string[];
  selectedNodeTypes: string[];
  selectedEdgeTypes: string[];
}

const GraphFilters: React.FC<GraphFiltersProps> = ({
  onNodeTypeFilterChange,
  onEdgeTypeFilterChange,
  nodeTypes,
  edgeTypes,
  selectedNodeTypes,
  selectedEdgeTypes,
}) => {
  const handleNodeTypeChange = (type: string) => {
    if (selectedNodeTypes.includes(type)) {
      onNodeTypeFilterChange(selectedNodeTypes.filter((t) => t !== type));
    } else {
      onNodeTypeFilterChange([...selectedNodeTypes, type]);
    }
  };

  const handleEdgeTypeChange = (type: string) => {
    if (selectedEdgeTypes.includes(type)) {
      onEdgeTypeFilterChange(selectedEdgeTypes.filter((t) => t !== type));
    } else {
      onEdgeTypeFilterChange([...selectedEdgeTypes, type]);
    }
  };

  const toggleAllNodeTypes = () => {
    if (selectedNodeTypes.length === nodeTypes.length) {
      onNodeTypeFilterChange([]);
    } else {
      onNodeTypeFilterChange([...nodeTypes]);
    }
  };

  const toggleAllEdgeTypes = () => {
    if (selectedEdgeTypes.length === edgeTypes.length) {
      onEdgeTypeFilterChange([]);
    } else {
      onEdgeTypeFilterChange([...edgeTypes]);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 p-2 rounded-md shadow-md space-y-2">
      <div>
        <div className="flex justify-between items-center mb-1">
          <h3 className="text-xs font-medium text-gray-900 dark:text-gray-100">Node Types</h3>
          <button
            className="text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
            onClick={toggleAllNodeTypes}
          >
            {selectedNodeTypes.length === nodeTypes.length ? 'Deselect All' : 'Select All'}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-1">
          {nodeTypes.map((type) => (
            <div key={type} className="flex items-center">
              <input
                type="checkbox"
                id={`node-type-${type}`}
                checked={selectedNodeTypes.includes(type)}
                onChange={() => handleNodeTypeChange(type)}
                className="h-3 w-3 text-blue-500"
              />
              <label
                htmlFor={`node-type-${type}`}
                className="ml-1 text-xs text-gray-700 dark:text-gray-300 truncate"
              >
                {getNodeConfig(type).label}
              </label>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="flex justify-between items-center mb-1">
          <h3 className="text-xs font-medium text-gray-900 dark:text-gray-100">Edge Types</h3>
          <button
            className="text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
            onClick={toggleAllEdgeTypes}
          >
            {selectedEdgeTypes.length === edgeTypes.length ? 'Deselect All' : 'Select All'}
          </button>
        </div>
        <div className="space-y-1">
          {edgeTypes.map((type) => (
            <div key={type} className="flex items-center">
              <input
                type="checkbox"
                id={`edge-type-${type}`}
                checked={selectedEdgeTypes.includes(type)}
                onChange={() => handleEdgeTypeChange(type)}
                className="h-3 w-3 text-blue-500"
              />
              <label
                htmlFor={`edge-type-${type}`}
                className="ml-1 text-xs text-gray-700 dark:text-gray-300 truncate"
              >
                {getEdgeConfig(type).label}
              </label>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default GraphFilters;
