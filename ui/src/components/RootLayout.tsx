import React from 'react';

import { Outlet } from 'react-router';

import { ChatPanel, ChatToggleButton } from './chat';
import { Sidebar } from './sidebar';

export const RootLayout: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  return (
    <div className="flex min-h-screen bg-dark-900">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <main className="flex-1 overflow-auto">{children ?? <Outlet />}</main>
      </div>
      <ChatPanel />
      <ChatToggleButton />
    </div>
  );
};
