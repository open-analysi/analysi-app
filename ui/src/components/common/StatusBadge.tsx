import React from 'react';

import { componentStyles } from '../../styles/components';
import { getStatusColor } from '../../utils/statusColors';

export const StatusBadge: React.FC<{ value: string }> = ({ value }) => {
  return (
    <span
      className={`
        ${componentStyles.badge}
        ${getStatusColor(value)}
      `}
    >
      {value}
    </span>
  );
};
