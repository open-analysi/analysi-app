import React, { useState, useEffect } from 'react';

import { SystemSource, generateMockSources } from '../../data/mockSettings';

const reliabilityBadgeClass = (score: number): string => {
  if (score >= 80) return 'bg-green-100 text-green-800';
  if (score >= 50) return 'bg-yellow-100 text-yellow-800';
  return 'bg-red-100 text-red-800';
};

const InternalKnowledge: React.FC = () => {
  const [sources, setSources] = useState<SystemSource[]>([]);

  useEffect(() => {
    setSources(generateMockSources());
  }, []);

  return (
    <div className="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6">
      <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
        Internal IT Knowledge
      </h2>
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
              System Information
            </h3>
            <p className="text-sm text-gray-500">
              Topology, naming conventions, and source reliability
            </p>
          </div>
          <button
            type="button"
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-[#FF3B81] hover:bg-[#FF1B6B]"
          >
            Add Information
          </button>
        </div>
        <div className="mt-4">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                  >
                    Source Name
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                  >
                    Reliability Score
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                  >
                    Comments
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                  >
                    Last Updated
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
                {sources.map((source) => (
                  <tr key={source.id}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-300">
                      {source.name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${reliabilityBadgeClass(source.reliabilityScore)}`}
                      >
                        {source.reliabilityScore}%
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                      {source.comments}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {source.lastUpdated.toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InternalKnowledge;
