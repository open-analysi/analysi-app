import React, { useState, useEffect } from 'react';

import { Runbook, generateMockRunbooks } from '../../data/mockSettings';

const CustomizeRunbooks: React.FC = () => {
  const [runbooks, setRunbooks] = useState<Runbook[]>([]);

  useEffect(() => {
    setRunbooks(generateMockRunbooks());
  }, []);

  return (
    <div className="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6">
      <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
        Customize Runbooks
      </h2>
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
              Available Runbooks
            </h3>
            <p className="text-sm text-gray-500">Manage your investigation runbooks</p>
          </div>
          <button
            type="button"
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-[#FF3B81] hover:bg-[#FF1B6B]"
          >
            Add New Runbook
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
                    Name
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                  >
                    Type
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                  >
                    Last Updated
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                  >
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
                {runbooks.map((runbook) => (
                  <tr key={runbook.id}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-300">
                      {runbook.name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full
                        ${runbook.type === 'System' ? 'bg-blue-100 text-blue-800' : 'bg-green-100 text-green-800'}`}
                      >
                        {runbook.type}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {runbook.lastUpdated.toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {runbook.isLocked ? (
                        <span className="text-red-500">Locked by {runbook.lockedBy}</span>
                      ) : (
                        <span className="text-green-500">Available</span>
                      )}
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

export default CustomizeRunbooks;
