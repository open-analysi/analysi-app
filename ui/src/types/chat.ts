/**
 * Chat types for the product chatbot (Project Rhodes).
 *
 * Matches the backend Pydantic schemas in analysi.schemas.chat.
 */

export interface PageContext {
  route: string;
  entity_type?: string;
  entity_id?: string;
}

export interface Conversation {
  id: string;
  tenant_id: string;
  user_id: string;
  title: string | null;
  page_context: PageContext | null;
  metadata: Record<string, unknown>;
  token_count_total: number;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  tenant_id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: { text: string } | string;
  tool_calls: unknown[] | null;
  token_count: number | null;
  model: string | null;
  latency_ms: number | null;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
}

/** SSE event types from the streaming endpoint */
export type SSEEvent =
  | { type: 'text_delta'; content: string }
  | { type: 'tool_call_start'; tool: string }
  | { type: 'tool_call_end'; tool: string }
  | { type: 'message_complete'; message_id: string; tokens: number; security_flags?: string[] }
  | { type: 'error'; message: string; code?: string };

/** Extract text from a ChatMessage content field */
export function getMessageText(msg: ChatMessage): string {
  if (typeof msg.content === 'string') return msg.content;
  if (msg.content && typeof msg.content === 'object') return msg.content.text ?? '';
  return '';
}
