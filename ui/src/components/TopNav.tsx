import React from 'react';

import { useOidc } from '@axa-fr/react-oidc';
import { ArrowRightStartOnRectangleIcon } from '@heroicons/react/24/outline';

export const TopNav: React.FC = () => {
  const { logout, isAuthenticated } = useOidc();

  const handleLogout = () => {
    void logout('/');
  };

  return (
    <div className="bg-dark-800 h-16 flex items-center justify-end px-6 border-b border-dark-700">
      {isAuthenticated && (
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-100 transition-colors px-3 py-1.5 rounded-md hover:bg-dark-700"
          title="Logout"
        >
          <ArrowRightStartOnRectangleIcon className="w-4 h-4" />
          <span>Logout</span>
        </button>
      )}
    </div>
  );
};
