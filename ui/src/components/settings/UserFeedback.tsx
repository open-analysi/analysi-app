import React, { useState, useEffect } from 'react';

import { FeedbackItem, generateMockFeedback } from '../../data/mockSettings';
import { componentStyles } from '../../styles/components';
import { StatusBadge } from '../common/StatusBadge';

const UserFeedback: React.FC = () => {
  const [feedbackItems, setFeedbackItems] = useState<FeedbackItem[]>([]);

  useEffect(() => {
    setFeedbackItems(generateMockFeedback());
  }, []);

  return (
    <div className={componentStyles.card}>
      <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
        User Input / Feedback
      </h2>
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
              Feedback History
            </h3>
            <p className="text-sm text-gray-500">View and manage alert investigation feedback</p>
          </div>
          <button type="button" className={componentStyles.primaryButton}>
            Add Feedback
          </button>
        </div>
        <div className="mt-4">
          <div className="overflow-x-auto">
            <table className={componentStyles.table}>
              <thead className={componentStyles.tableHeader}>
                <tr>
                  <th className={componentStyles.tableHeaderCell}>Feedback</th>
                  <th className={componentStyles.tableHeaderCell}>Provided By</th>
                  <th className={componentStyles.tableHeaderCell}>Alert</th>
                  <th className={componentStyles.tableHeaderCell}>Severity</th>
                  <th className={componentStyles.tableHeaderCell}>Date</th>
                </tr>
              </thead>
              <tbody className={componentStyles.tableBody}>
                {feedbackItems.map((item) => (
                  <tr key={item.id}>
                    <td className={componentStyles.tableCell}>{item.text}</td>
                    <td className={componentStyles.tableCell}>{item.providedBy}</td>
                    <td className={componentStyles.tableCell}>{item.relatedAlert}</td>
                    <td className={componentStyles.tableCell}>
                      <StatusBadge value={item.severity} />
                    </td>
                    <td className={componentStyles.tableCell}>
                      {item.dateTime.toLocaleDateString()}
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

export default UserFeedback;
