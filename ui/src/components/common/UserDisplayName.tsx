import React from 'react';

import { useUserDisplay } from '../../hooks/useUserDisplay';

/** Small wrapper so we can call useUserDisplay inside a .map() loop */
const UserDisplayName: React.FC<{ userId: string | undefined }> = ({ userId }) => {
  const display = useUserDisplay(userId);
  return <>{display}</>;
};

export default UserDisplayName;
