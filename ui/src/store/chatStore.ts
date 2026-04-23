/**
 * Chat store — Zustand state for the product chatbot (Project Rhodes).
 *
 * Manages: panel open/closed, conversations list, active conversation,
 * message streaming state, and suggested prompts.
 */

import { create } from 'zustand';

import * as chatApi from '../services/chatApi';
import type {
  Conversation,
  ConversationDetail,
  ChatMessage,
  PageContext,
  SSEEvent,
} from '../types/chat';
import { logger } from '../utils/errorHandler';

// --- Suggested prompts per page context ---

const SUGGESTED_PROMPTS: Record<string, string[]> = {
  alerts: [
    'Show me all high-severity alerts',
    'What is the disposition of the SQL injection alert?',
    'Have we seen IP 167.99.169.17 in any alerts?',
  ],
  workflows: [
    'List all workflows ranked by complexity',
    'How do I create a new workflow?',
    'Compare the two SQL injection workflows',
  ],
  tasks: ['List tasks by category', 'How do I create a new task?', 'Which tasks use Splunk?'],
  integrations: ['Which integrations are healthy?', 'How do I set up a new integration?'],
  knowledge: ['What Knowledge Units are available?', 'Search knowledge base for Splunk tools'],
  settings: ['What roles are available?', 'Show recent audit trail events'],
  default: [
    'What can you help me with?',
    'Show me the platform overview',
    'How do I analyze an alert?',
  ],
};

function getSuggestedPrompts(pageContext: PageContext | null): string[] {
  if (!pageContext?.route) return SUGGESTED_PROMPTS.default;
  const segment = pageContext.route.replace(/^\//, '').split('/')[0];
  return SUGGESTED_PROMPTS[segment] ?? SUGGESTED_PROMPTS.default;
}

// --- Store types ---

interface StreamingMessage {
  /** Accumulated text from text_delta events */
  text: string;
  /** True while the stream is active */
  isStreaming: boolean;
  /** Tool currently being executed (null when streaming text) */
  activeTool: string | null;
}

export interface ChatState {
  // Panel
  isOpen: boolean;
  togglePanel: () => void;
  openPanel: () => void;
  closePanel: () => void;

  // Conversations
  conversations: Conversation[];
  activeConversation: ConversationDetail | null;
  isLoadingConversations: boolean;
  isLoadingMessages: boolean;

  // Streaming
  streamingMessage: StreamingMessage | null;
  abortController: AbortController | null;

  // Error state
  error: string | null;
  errorCode: string | null;
  clearError: () => void;

  // Context
  pageContext: PageContext | null;
  suggestedPrompts: string[];

  // Actions
  setPageContext: (ctx: PageContext | null) => void;
  fetchConversations: () => Promise<void>;
  createConversation: (pageContext?: PageContext | null) => Promise<string | null>;
  selectConversation: (conversationId: string) => Promise<void>;
  deleteConversation: (conversationId: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  stopStreaming: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  // --- Panel state ---
  isOpen: false,
  togglePanel: () => set((s) => ({ isOpen: !s.isOpen })),
  openPanel: () => set({ isOpen: true }),
  closePanel: () => set({ isOpen: false }),

  // --- Conversations ---
  conversations: [],
  activeConversation: null,
  isLoadingConversations: false,
  isLoadingMessages: false,
  streamingMessage: null,
  abortController: null,

  // --- Error ---
  error: null,
  errorCode: null,
  clearError: () => set({ error: null, errorCode: null }),

  // --- Context ---
  pageContext: null,
  suggestedPrompts: SUGGESTED_PROMPTS.default,

  setPageContext: (ctx) =>
    set({
      pageContext: ctx,
      suggestedPrompts: getSuggestedPrompts(ctx),
    }),

  // --- Actions ---

  fetchConversations: async () => {
    set({ isLoadingConversations: true });
    try {
      const { conversations } = await chatApi.listConversations({ limit: 50 });
      set({ conversations });
    } catch (err) {
      logger.error('Failed to fetch conversations', err, {
        component: 'ChatStore',
        method: 'fetchConversations',
      });
      // Don't show error for conversation list — it's not critical
    } finally {
      set({ isLoadingConversations: false });
    }
  },

  createConversation: async (pageContext) => {
    set({ error: null });
    try {
      const conversation = await chatApi.createConversation({
        page_context: pageContext ?? get().pageContext,
      });
      set((s) => ({
        conversations: [conversation, ...s.conversations],
        activeConversation: { ...conversation, messages: [] },
      }));
      return conversation.id;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create conversation';
      logger.error('Failed to create conversation', err, {
        component: 'ChatStore',
        method: 'createConversation',
      });
      set({ error: `Could not connect to chat service. ${msg}` });
      return null;
    }
  },

  selectConversation: async (conversationId) => {
    set({ isLoadingMessages: true, error: null });
    try {
      const detail = await chatApi.getConversation(conversationId);
      set({ activeConversation: detail });
    } catch (err) {
      logger.error('Failed to load conversation', err, {
        component: 'ChatStore',
        method: 'selectConversation',
      });
      set({ error: 'Failed to load conversation' });
    } finally {
      set({ isLoadingMessages: false });
    }
  },

  deleteConversation: async (conversationId) => {
    try {
      await chatApi.deleteConversation(conversationId);
      set((s) => ({
        conversations: s.conversations.filter((c) => c.id !== conversationId),
        activeConversation:
          s.activeConversation?.id === conversationId ? null : s.activeConversation,
      }));
    } catch (err) {
      logger.error('Failed to delete conversation', err, {
        component: 'ChatStore',
        method: 'deleteConversation',
      });
    }
  },

  sendMessage: async (content) => {
    const { activeConversation, pageContext } = get();
    set({ error: null });

    // Auto-create conversation if none active
    let conversationId: string | undefined = activeConversation?.id;
    if (!conversationId) {
      const newId = await get().createConversation();
      if (!newId) return; // Creation failed — error already set
      conversationId = newId;
    }

    // Optimistic: add user message to UI immediately
    const userMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      conversation_id: conversationId,
      tenant_id: '',
      role: 'user',
      content: { text: content },
      tool_calls: null,
      token_count: null,
      model: null,
      latency_ms: null,
      created_at: new Date().toISOString(),
    };

    set((s) => ({
      activeConversation: s.activeConversation
        ? { ...s.activeConversation, messages: [...s.activeConversation.messages, userMessage] }
        : s.activeConversation,
      streamingMessage: { text: '', isStreaming: true, activeTool: null },
    }));

    // Start SSE stream
    const controller = chatApi.sendMessageStream(
      conversationId,
      content,
      pageContext,
      // onEvent
      (event: SSEEvent) => {
        if (event.type === 'text_delta') {
          set((s) => ({
            streamingMessage: s.streamingMessage
              ? {
                  ...s.streamingMessage,
                  text: s.streamingMessage.text + event.content,
                  activeTool: null,
                }
              : { text: event.content, isStreaming: true, activeTool: null },
          }));
        } else if (event.type === 'tool_call_start') {
          set((s) => ({
            streamingMessage: s.streamingMessage
              ? { ...s.streamingMessage, activeTool: event.tool }
              : { text: '', isStreaming: true, activeTool: event.tool },
          }));
        } else if (event.type === 'tool_call_end') {
          set((s) => ({
            streamingMessage: s.streamingMessage
              ? { ...s.streamingMessage, activeTool: null }
              : s.streamingMessage,
          }));
        } else if (event.type === 'message_complete') {
          // Finalize: add assistant message to conversation
          const finalText = get().streamingMessage?.text ?? '';
          const assistantMessage: ChatMessage = {
            id: event.message_id,
            conversation_id: conversationId,
            tenant_id: '',
            role: 'assistant',
            content: { text: finalText },
            tool_calls: null,
            token_count: event.tokens,
            model: null,
            latency_ms: null,
            created_at: new Date().toISOString(),
          };
          set((s) => ({
            activeConversation: s.activeConversation
              ? {
                  ...s.activeConversation,
                  messages: [...s.activeConversation.messages, assistantMessage],
                }
              : s.activeConversation,
            streamingMessage: null,
            abortController: null,
          }));
        } else if (event.type === 'error') {
          set({
            error: event.message,
            errorCode: event.code ?? null,
            streamingMessage: null,
            abortController: null,
          });
        }
      },
      // onDone
      () => {
        set((s) => ({
          streamingMessage: s.streamingMessage?.isStreaming ? null : s.streamingMessage,
          abortController: null,
        }));
      },
      // onError
      (err) => {
        logger.error('Chat stream failed', err, {
          component: 'ChatStore',
          method: 'sendMessage',
        });
        set({
          error: 'Failed to get a response. Please try again.',
          errorCode: null,
          streamingMessage: null,
          abortController: null,
        });
      }
    );

    set({ abortController: controller });
  },

  stopStreaming: () => {
    const { abortController } = get();
    if (abortController) {
      abortController.abort();
      set({ streamingMessage: null, abortController: null });
    }
  },
}));
