import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { mockGet } = vi.hoisted(() => ({
  mockGet: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: mockGet,
      post: vi.fn(),
      put: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
      interceptors: {
        request: { use: vi.fn(), eject: vi.fn() },
        response: { use: vi.fn(), eject: vi.fn() },
      },
    })),
  },
}));

vi.mock('../../utils/errorHandler', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { getCurrentUser, resolveUsers } from '../usersApi';

const SYSTEM_USER = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'system@analysi.internal',
  display_name: 'System',
};

const DEV_USER = {
  id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
  email: 'dev@analysi.local',
  display_name: 'Dev User',
};

describe('usersApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ==================== getCurrentUser ====================

  describe('getCurrentUser', () => {
    it('should fetch current user via GET /users/me', async () => {
      mockGet.mockResolvedValueOnce({
        data: { data: DEV_USER, meta: { request_id: 'req-1' } },
      });

      const result = await getCurrentUser();

      expect(mockGet).toHaveBeenCalledWith('/users/me');
      expect(result).toEqual(DEV_USER);
    });
  });

  // ==================== resolveUsers ====================

  describe('resolveUsers', () => {
    it('should return empty array when no ids provided', async () => {
      const result = await resolveUsers([]);

      expect(mockGet).not.toHaveBeenCalled();
      expect(result).toEqual([]);
    });

    it('should unwrap Sifnos envelope and return user profiles', async () => {
      // The backend returns { data: UserProfile[], meta: {...} }
      // NOT { data: { users: UserProfile[] }, meta: {...} }
      mockGet.mockResolvedValueOnce({
        data: {
          data: [SYSTEM_USER, DEV_USER],
          meta: { request_id: 'req-2', total: 2 },
        },
      });

      const result = await resolveUsers([SYSTEM_USER.id, DEV_USER.id]);

      expect(mockGet).toHaveBeenCalledWith('/users/resolve', {
        params: { ids: [SYSTEM_USER.id, DEV_USER.id] },
        paramsSerializer: { indexes: null },
      });
      expect(result).toEqual([SYSTEM_USER, DEV_USER]);
    });

    it('should resolve a single user', async () => {
      mockGet.mockResolvedValueOnce({
        data: {
          data: [SYSTEM_USER],
          meta: { request_id: 'req-3', total: 1 },
        },
      });

      const result = await resolveUsers([SYSTEM_USER.id]);

      expect(result).toHaveLength(1);
      expect(result[0].display_name).toBe('System');
    });

    it('should propagate API errors', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network error'));

      await expect(resolveUsers([SYSTEM_USER.id])).rejects.toThrow('Network error');
    });
  });
});
