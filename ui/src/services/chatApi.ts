/**
 * Chat API service for the product chatbot (Project Rhodes).
 *
 * Conversation CRUD uses the standard Sifnos envelope helpers.
 * Message streaming uses raw fetch (not Axios) because Axios doesn't
 * support ReadableStream for SSE consumption, and we need the
 * Authorization header (can't use native EventSource).
 */

import { useAuthStore } from '../store/authStore';
import type { Conversation, ConversationDetail, PageContext, SSEEvent } from '../types/chat';

import { fetchList, fetchOne, mutateOne, apiDelete, withApi } from './apiClient';

const BASE = '/chat/conversations';

// --- Conversation CRUD ---

export const createConversation = (body: {
  title?: string;
  page_context?: PageContext | null;
}): Promise<Conversation> =>
  withApi('createConversation', 'creating conversation', () =>
    mutateOne<Conversation>('post', BASE, body)
  );

export const listConversations = (
  params: { limit?: number; offset?: number } = {}
): Promise<{ conversations: Conversation[]; total: number }> =>
  withApi('listConversations', 'fetching conversations', () =>
    fetchList<'conversations', Conversation>(BASE, 'conversations', { params })
  );

export const getConversation = (conversationId: string): Promise<ConversationDetail> =>
  withApi('getConversation', 'fetching conversation', () =>
    fetchOne<ConversationDetail>(`${BASE}/${conversationId}`)
  );

export const updateConversationTitle = (
  conversationId: string,
  title: string
): Promise<Conversation> =>
  withApi('updateConversationTitle', 'updating conversation title', () =>
    mutateOne<Conversation>('patch', `${BASE}/${conversationId}`, { title })
  );

export const deleteConversation = (conversationId: string): Promise<void> =>
  withApi('deleteConversation', 'deleting conversation', () =>
    apiDelete(`${BASE}/${conversationId}`)
  );

// --- SSE Streaming ---

/**
 * Build the full URL for the streaming endpoint, injecting the tenant.
 * We use raw fetch (not Axios) because Axios doesn't support ReadableStream.
 */
function buildStreamUrl(conversationId: string): string {
  const { tenant_id } = useAuthStore.getState();
  return `/api/v1/${tenant_id}${BASE}/${conversationId}/messages`;
}

/**
 * Get the auth headers for fetch calls (mirrors the Axios interceptor).
 * Supports both Bearer token (Keycloak) and API key (dev/E2E mode).
 */
function getAuthHeaders(): Record<string, string> {
  const { accessToken } = useAuthStore.getState();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  } else {
    const apiKey = import.meta.env.VITE_E2E_API_KEY as string | undefined;
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }
  }
  return headers;
}

/**
 * Send a message and consume the SSE stream.
 *
 * Calls the onEvent callback for each parsed SSE event.
 * Returns the AbortController so the caller can cancel the stream.
 */
export function sendMessageStream(
  conversationId: string,
  content: string,
  pageContext: PageContext | null,
  onEvent: (event: SSEEvent) => void,
  onDone: () => void,
  onError: (error: Error) => void
): AbortController {
  const controller = new AbortController();

  const url = buildStreamUrl(conversationId);
  const body = JSON.stringify({ content, page_context: pageContext });

  void consumeSSEStream(url, body, controller.signal, onEvent, onDone, onError);

  return controller;
}

/**
 * Parse a single SSE line. Returns true if the stream is done.
 */
function parseSSELine(
  line: string,
  onEvent: (event: SSEEvent) => void,
  onDone: () => void
): boolean {
  const trimmed = line.trim();
  if (!trimmed || !trimmed.startsWith('data: ')) return false;

  const data = trimmed.slice(6);
  if (data === '[DONE]') {
    onDone();
    return true;
  }

  try {
    onEvent(JSON.parse(data) as SSEEvent);
  } catch {
    // Skip malformed JSON lines
  }
  return false;
}

/**
 * Read an SSE response body, parsing lines and dispatching events.
 * Returns when [DONE] is received or the stream ends.
 */
async function readSSEBody(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (event: SSEEvent) => void,
  onDone: () => void
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (parseSSELine(line, onEvent, onDone)) return;
    }
  }

  onDone();
}

/**
 * Internal: fetch and consume an SSE stream.
 */
async function consumeSSEStream(
  url: string,
  body: string,
  signal: AbortSignal,
  onEvent: (event: SSEEvent) => void,
  onDone: () => void,
  onError: (error: Error) => void
): Promise<void> {
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: getAuthHeaders(),
      body,
      signal,
    });

    if (!response.ok) throw new Error(`Chat API error: ${response.status}`);
    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    await readSSEBody(reader, onEvent, onDone);
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      onDone();
    } else {
      onError(err instanceof Error ? err : new Error(String(err)));
    }
  }
}
