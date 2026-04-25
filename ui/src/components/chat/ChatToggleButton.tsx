import React from 'react';

import { ChatBubbleLeftRightIcon } from '@heroicons/react/24/outline';

import { useChatStore } from '../../store/chatStore';

/**
 * Floating toggle button for opening/closing the chat panel.
 * Placed in the bottom-right corner of the viewport.
 */
export const ChatToggleButton: React.FC = () => {
  const { isOpen, togglePanel } = useChatStore();

  // Hide the button when panel is open (panel has its own close button)
  if (isOpen) return null;

  return (
    <button
      onClick={togglePanel}
      className="fixed bottom-6 right-6 z-40 w-12 h-12 rounded-full bg-primary text-white shadow-lg hover:bg-primary/90 transition-all hover:scale-105 flex items-center justify-center"
      title="Open Analysi Chat"
      aria-label="Open chat panel"
    >
      <ChatBubbleLeftRightIcon className="w-6 h-6" />
    </button>
  );
};
