/**
 * Script Completion API
 *
 * Provides AI-assisted inline completions for the Cy script editor.
 * Calls POST /v1/{tenant}/tasks/autocomplete on the backend.
 */

import { backendApiClient } from './apiClient';

export interface ScriptCompletionRequest {
  /** Everything in the editor before the cursor */
  prefix: string;
  /** Everything after the cursor (context only) */
  suffix?: string;
  /** Why autocomplete fired */
  trigger_kind?: 'invoked' | 'character' | 'newline';
  /** The character that triggered it, if trigger_kind is "character" */
  trigger_character?: string | null;
}

interface AutocompleteCompletion {
  insert_text: string;
  label: string;
  detail: string;
  kind: string;
}

/**
 * Request a script completion from the AI backend.
 * Returns the insert_text of the first completion, or null if none.
 */
export async function getScriptCompletion(
  request: ScriptCompletionRequest
): Promise<string | null> {
  const response = await backendApiClient.post<{ completions: AutocompleteCompletion[] }>(
    '/tasks/autocomplete',
    {
      script_prefix: request.prefix,
      script_suffix: request.suffix ?? '',
      trigger_kind: request.trigger_kind ?? 'invoked',
      trigger_character: request.trigger_character ?? null,
    }
  );

  const completions = response.data?.completions;
  if (!completions || completions.length === 0) return null;
  return completions[0].insert_text || null;
}
