import React, { useEffect, useRef, useCallback } from 'react';

import {
  XMarkIcon,
  PlusIcon,
  ChatBubbleLeftRightIcon,
  TrashIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { Link, useLocation } from 'react-router';

import { useChatStore } from '../../store/chatStore';
import type { PageContext } from '../../types/chat';

import { ChatInput } from './ChatInput';
import { ChatMessage } from './ChatMessage';
import { StreamingMessage } from './StreamingMessage';
import { SuggestedPrompts } from './SuggestedPrompts';

/**
 * Right sidebar chat panel — the main chatbot UI.
 *
 * Renders as an overlay drawer on the right side of the screen.
 * Persists across page navigation; updates page context on route change.
 */
export const ChatPanel: React.FC = () => {
  const location = useLocation();

  const {
    isOpen,
    closePanel,
    activeConversation,
    conversations,
    streamingMessage,
    suggestedPrompts,
    isLoadingMessages,
    error,
    errorCode,
    clearError,
    setPageContext,
    fetchConversations,
    createConversation,
    selectConversation,
    deleteConversation,
    sendMessage,
    stopStreaming,
  } = useChatStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);
  const [showConversationList, setShowConversationList] = React.useState(false);

  // Track whether user has scrolled away from bottom
  const handleScroll = useCallback(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    // "At bottom" = within 80px of the bottom edge
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    userScrolledUpRef.current = !atBottom;
  }, []);

  // Update page context on route change
  useEffect(() => {
    const segments = location.pathname.replace(/^\//, '').split('/');
    const section = segments[0] ?? '';
    const entityId = segments[1];

    const ctx: PageContext = {
      route: location.pathname,
      entity_type: entityId ? section.replace(/s$/, '') : undefined,
      entity_id: entityId,
    };

    setPageContext(ctx);
  }, [location.pathname, setPageContext]);

  // Fetch conversations when panel opens
  useEffect(() => {
    if (isOpen) {
      void fetchConversations();
    }
  }, [isOpen, fetchConversations]);

  // Auto-scroll to bottom — but only if user hasn't scrolled up
  useEffect(() => {
    if (!userScrolledUpRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [activeConversation?.messages, streamingMessage?.text]);

  // Reset scroll lock when streaming finishes (new message complete)
  useEffect(() => {
    if (!streamingMessage) {
      userScrolledUpRef.current = false;
    }
  }, [streamingMessage]);

  const handleSend = useCallback(
    (content: string) => {
      void sendMessage(content);
    },
    [sendMessage]
  );

  const handleNewConversation = useCallback(() => {
    void createConversation().then(() => setShowConversationList(false));
  }, [createConversation]);

  if (!isOpen) return null;

  const messages = activeConversation?.messages ?? [];
  const hasMessages = messages.length > 0 || streamingMessage;
  const isSending = !!streamingMessage?.isStreaming;

  return (
    <div className="fixed right-0 top-0 h-screen w-[420px] bg-dark-900 border-l border-dark-600 flex flex-col z-50 shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-dark-600">
        <div className="flex items-center gap-2">
          <ChatBubbleLeftRightIcon className="w-5 h-5 text-primary" />
          <h2 className="text-sm font-semibold text-gray-200">
            {activeConversation?.title ?? 'Analysi Chat'}
          </h2>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowConversationList(!showConversationList)}
            className="p-1.5 rounded-md text-gray-400 hover:text-gray-200 hover:bg-dark-700 transition-colors"
            title="Conversations"
          >
            <ChatBubbleLeftRightIcon className="w-4 h-4" />
          </button>
          <button
            onClick={handleNewConversation}
            className="p-1.5 rounded-md text-gray-400 hover:text-gray-200 hover:bg-dark-700 transition-colors"
            title="New conversation"
          >
            <PlusIcon className="w-4 h-4" />
          </button>
          <button
            onClick={closePanel}
            className="p-1.5 rounded-md text-gray-400 hover:text-gray-200 hover:bg-dark-700 transition-colors"
            title="Close chat"
          >
            <XMarkIcon className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && errorCode === 'no_ai_provider' && (
        <div className="px-4 py-3 bg-amber-500/10 border-b border-amber-500/20">
          <div className="flex items-start gap-2">
            <ExclamationTriangleIcon className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-xs font-medium text-amber-300 mb-1">AI integration required</p>
              <p className="text-xs text-amber-200/70 mb-2">
                Connect an AI provider to start using the chat assistant.
              </p>
              <Link
                to="/integrations"
                onClick={closePanel}
                className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:text-primary-light transition-colors"
              >
                Set up integration →
              </Link>
            </div>
          </div>
        </div>
      )}
      {error && errorCode === 'ai_provider_error' && (
        <div className="px-4 py-3 bg-amber-500/10 border-b border-amber-500/20">
          <div className="flex items-start gap-2">
            <ExclamationTriangleIcon className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-xs font-medium text-amber-300 mb-1">
                AI integration misconfigured
              </p>
              <p className="text-xs text-amber-200/70 mb-2">{error}</p>
              <Link
                to="/integrations"
                onClick={closePanel}
                className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:text-primary-light transition-colors"
              >
                Check integrations →
              </Link>
            </div>
          </div>
        </div>
      )}
      {error && errorCode !== 'no_ai_provider' && errorCode !== 'ai_provider_error' && (
        <div className="flex items-start gap-2 px-4 py-2.5 bg-red-500/10 border-b border-red-500/20">
          <ExclamationTriangleIcon className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-red-300 flex-1">{error}</p>
          <button
            onClick={clearError}
            className="text-red-400 hover:text-red-300 flex-shrink-0"
            title="Dismiss error"
          >
            <XMarkIcon className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Conversation list dropdown */}
      {showConversationList && (
        <div className="border-b border-dark-600 max-h-[240px] overflow-y-auto bg-dark-800">
          {conversations.length === 0 ? (
            <p className="text-xs text-gray-500 p-3 text-center">No conversations yet</p>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={`flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-dark-700 transition-colors ${
                  activeConversation?.id === conv.id ? 'bg-dark-700' : ''
                }`}
              >
                <button
                  onClick={() => {
                    void selectConversation(conv.id);
                    setShowConversationList(false);
                  }}
                  className="flex-1 text-left"
                >
                  <p className="text-xs text-gray-300 truncate">
                    {conv.title ?? 'Untitled conversation'}
                  </p>
                  <p className="text-[10px] text-gray-500">
                    {new Date(conv.updated_at).toLocaleDateString()}
                  </p>
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    void deleteConversation(conv.id);
                  }}
                  className="p-1 rounded text-gray-500 hover:text-red-400 hover:bg-dark-600 transition-colors"
                  title="Delete conversation"
                >
                  <TrashIcon className="w-3.5 h-3.5" />
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {/* Messages area */}
      <div ref={messagesContainerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto">
        {isLoadingMessages && (
          <div className="flex items-center justify-center h-full">
            <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
          </div>
        )}
        {!isLoadingMessages && hasMessages && (
          <>
            {messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
            {streamingMessage && (
              <StreamingMessage
                text={streamingMessage.text}
                activeTool={streamingMessage.activeTool}
              />
            )}
            <div ref={messagesEndRef} />
          </>
        )}
        {!isLoadingMessages && !hasMessages && (
          <SuggestedPrompts prompts={suggestedPrompts} onSelect={handleSend} />
        )}
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} onStop={stopStreaming} isStreaming={isSending} />
    </div>
  );
};
