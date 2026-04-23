import React from 'react';

import { useSettingsStore } from '../../store/settingsStore';
import { componentStyles } from '../../styles/components';

export const ConfigurationHistory: React.FC<{ hideTitle?: boolean }> = ({ hideTitle }) => {
  const { versions, revertToVersion } = useSettingsStore();

  return (
    <div className={componentStyles.card}>
      {!hideTitle && (
        <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
          Configuration History
        </h2>
      )}
      <div className="overflow-x-auto">
        <table className={componentStyles.table}>
          <thead className={componentStyles.tableHeader}>
            <tr>
              <th className={componentStyles.tableHeaderCell}>Date</th>
              <th className={componentStyles.tableHeaderCell}>Author</th>
              <th className={componentStyles.tableHeaderCell}>Changes</th>
              <th className={componentStyles.tableHeaderCell}>Comment</th>
              <th className={componentStyles.tableHeaderCell}>Actions</th>
            </tr>
          </thead>
          <tbody className={componentStyles.tableBody}>
            {versions.map((version) => (
              <tr key={version.id}>
                <td className={componentStyles.tableCell}>{version.timestamp.toLocaleString()}</td>
                <td className={componentStyles.tableCell}>{version.author}</td>
                <td className={componentStyles.tableCell}>
                  <ul className="list-disc list-inside">
                    {version.changes.map((change, idx) => (
                      <li key={idx}>
                        {change.component}: {change.field} changed
                      </li>
                    ))}
                  </ul>
                </td>
                <td className={componentStyles.tableCell}>{version.comment}</td>
                <td className={componentStyles.tableCell}>
                  <button
                    onClick={() => revertToVersion(version.id)}
                    className="text-blue-600 hover:text-blue-800"
                  >
                    Revert to this version
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
