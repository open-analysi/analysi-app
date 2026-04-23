import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock the apiClient module before importing scriptCompletionApi
vi.mock('../apiClient', () => ({
  backendApiClient: {
    post: vi.fn(),
  },
}));

import { backendApiClient } from '../apiClient';
import { getScriptCompletion } from '../scriptCompletionApi';

const mockPost = vi.mocked(backendApiClient.post);

describe('getScriptCompletion', () => {
  beforeEach(() => {
    mockPost.mockReset();
  });

  // -------------------------------------------------------------------------
  // Request mapping
  // -------------------------------------------------------------------------

  it('maps prefix to script_prefix in the request body', async () => {
    mockPost.mockResolvedValue({ data: { completions: [] } });

    await getScriptCompletion({ prefix: 'alert = input\n' });

    expect(mockPost).toHaveBeenCalledWith(
      '/tasks/autocomplete',
      expect.objectContaining({ script_prefix: 'alert = input\n' })
    );
  });

  it('maps suffix to script_suffix in the request body', async () => {
    mockPost.mockResolvedValue({ data: { completions: [] } });

    await getScriptCompletion({ prefix: 'alert = input\n', suffix: 'return alert' });

    expect(mockPost).toHaveBeenCalledWith(
      '/tasks/autocomplete',
      expect.objectContaining({ script_suffix: 'return alert' })
    );
  });

  it('sends empty string for script_suffix when suffix is not provided', async () => {
    mockPost.mockResolvedValue({ data: { completions: [] } });

    await getScriptCompletion({ prefix: 'alert = input\n' });

    expect(mockPost).toHaveBeenCalledWith(
      '/tasks/autocomplete',
      expect.objectContaining({ script_suffix: '' })
    );
  });

  it('passes trigger_kind when provided', async () => {
    mockPost.mockResolvedValue({ data: { completions: [] } });

    await getScriptCompletion({ prefix: 'alert = input\n', trigger_kind: 'newline' });

    expect(mockPost).toHaveBeenCalledWith(
      '/tasks/autocomplete',
      expect.objectContaining({ trigger_kind: 'newline' })
    );
  });

  it('defaults trigger_kind to "invoked" when not provided', async () => {
    mockPost.mockResolvedValue({ data: { completions: [] } });

    await getScriptCompletion({ prefix: 'alert = input\n' });

    expect(mockPost).toHaveBeenCalledWith(
      '/tasks/autocomplete',
      expect.objectContaining({ trigger_kind: 'invoked' })
    );
  });

  it('passes trigger_character when provided', async () => {
    mockPost.mockResolvedValue({ data: { completions: [] } });

    await getScriptCompletion({
      prefix: 'result = ip_r',
      trigger_kind: 'character',
      trigger_character: 'r',
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/tasks/autocomplete',
      expect.objectContaining({ trigger_character: 'r' })
    );
  });

  it('sends null for trigger_character when not provided', async () => {
    mockPost.mockResolvedValue({ data: { completions: [] } });

    await getScriptCompletion({ prefix: 'alert = input\n' });

    expect(mockPost).toHaveBeenCalledWith(
      '/tasks/autocomplete',
      expect.objectContaining({ trigger_character: null })
    );
  });

  // -------------------------------------------------------------------------
  // Response handling
  // -------------------------------------------------------------------------

  it('returns insert_text of the first completion', async () => {
    mockPost.mockResolvedValue({
      data: {
        completions: [
          { insert_text: 'src_ip = alert["src_ip"] ?? null', label: 'src_ip', detail: '', kind: 'variable' },
          { insert_text: 'dst_ip = alert["dst_ip"] ?? null', label: 'dst_ip', detail: '', kind: 'variable' },
        ],
      },
    });

    const result = await getScriptCompletion({ prefix: 'alert = input\n' });

    expect(result).toBe('src_ip = alert["src_ip"] ?? null');
  });

  it('returns null when completions array is empty', async () => {
    mockPost.mockResolvedValue({ data: { completions: [] } });

    const result = await getScriptCompletion({ prefix: 'alert = input\n' });

    expect(result).toBeNull();
  });

  it('returns null when response has no completions property', async () => {
    mockPost.mockResolvedValue({ data: {} });

    const result = await getScriptCompletion({ prefix: 'alert = input\n' });

    expect(result).toBeNull();
  });

  it('returns null when response data is null', async () => {
    mockPost.mockResolvedValue({ data: null });

    const result = await getScriptCompletion({ prefix: 'alert = input\n' });

    expect(result).toBeNull();
  });

  it('returns null when first completion has empty insert_text', async () => {
    mockPost.mockResolvedValue({
      data: {
        completions: [{ insert_text: '', label: 'empty', detail: '', kind: 'variable' }],
      },
    });

    const result = await getScriptCompletion({ prefix: 'alert = input\n' });

    expect(result).toBeNull();
  });

  it('propagates API errors to the caller', async () => {
    mockPost.mockRejectedValue(new Error('Network error'));

    await expect(getScriptCompletion({ prefix: 'alert = input\n' })).rejects.toThrow(
      'Network error'
    );
  });

  it('calls POST /tasks/autocomplete endpoint', async () => {
    mockPost.mockResolvedValue({ data: { completions: [] } });

    await getScriptCompletion({ prefix: 'test' });

    expect(mockPost).toHaveBeenCalledWith('/tasks/autocomplete', expect.any(Object));
  });
});
