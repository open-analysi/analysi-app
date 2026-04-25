import React from 'react';

import { NODE_TYPE_CONFIG, EDGE_TYPE_CONFIG } from '../../../types/kdg';

interface GraphLegendProps {
  className?: string;
}

const GraphLegend: React.FC<GraphLegendProps> = ({ className }) => {
  return (
    <div className={`bg-white dark:bg-gray-800 p-2 rounded-md shadow-md text-xs ${className}`}>
      <div className="flex flex-wrap items-center">
        {/* Node types */}
        <div className="mr-6">
          {Object.entries(NODE_TYPE_CONFIG).map(([type, config]) => (
            <div key={type} className="flex items-center mr-2 inline-block">
              <span className="mr-1">{config.emoji}</span>
              <span className="mr-2 text-gray-900 dark:text-gray-100">{config.label}</span>
            </div>
          ))}
        </div>

        {/* Line between sections */}
        <div className="h-6 border-r border-gray-300 dark:border-gray-600 mx-2"></div>

        {/* Edge types */}
        <div>
          {Object.entries(EDGE_TYPE_CONFIG).map(([type, config]) => (
            <div key={type} className="flex items-center mr-2 inline-block">
              <div
                className="w-6 h-0 mr-1 border-t-2"
                style={{
                  borderColor: config.color,
                  borderStyle: config.style,
                }}
              />
              <span className="text-gray-900 dark:text-gray-100">{config.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default GraphLegend;
