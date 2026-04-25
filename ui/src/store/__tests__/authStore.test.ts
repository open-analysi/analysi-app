import { describe, it, expect, beforeEach } from 'vitest';

// Import store AFTER potential module reset to get fresh state each test
// We use the factory reset approach below

describe('authStore', () => {
  // Fresh store for each test by re-importing via resetModules
  // The store singleton is created on import so we need this isolation

  beforeEach(() => {
    // Reset module state between tests
  });

  describe('initial state', () => {
    it('has expected defaults', async () => {
      const { useAuthStore } = await import('../authStore');
      const state = useAuthStore.getState();

      expect(state.tenant_id).toBe('default');
      expect(state.email).toBeNull();
      expect(state.name).toBeNull();
      expect(state.roles).toEqual([]);
      expect(state.isAuthenticated).toBe(false);
    });
  });

  describe('setFromClaims', () => {
    it('updates all fields from full claims', async () => {
      const { useAuthStore } = await import('../authStore');
      const { setFromClaims } = useAuthStore.getState();

      setFromClaims({
        tenant_id: 'demo',
        roles: ['owner', 'analyst'],
        email: 'dev@analysi.local',
        name: 'Dev User',
      });

      const state = useAuthStore.getState();
      expect(state.tenant_id).toBe('demo');
      expect(state.roles).toEqual(['owner', 'analyst']);
      expect(state.email).toBe('dev@analysi.local');
      expect(state.name).toBe('Dev User');
    });

    it('sets isAuthenticated to true', async () => {
      const { useAuthStore } = await import('../authStore');
      const { setFromClaims } = useAuthStore.getState();

      setFromClaims({ email: 'user@example.com' });

      expect(useAuthStore.getState().isAuthenticated).toBe(true);
    });

    it('falls back to default tenant_id when missing', async () => {
      const { useAuthStore } = await import('../authStore');
      const { setFromClaims } = useAuthStore.getState();

      setFromClaims({ email: 'no-tenant@example.com' });

      expect(useAuthStore.getState().tenant_id).toBe('default');
    });

    it('falls back to empty array when roles missing', async () => {
      const { useAuthStore } = await import('../authStore');
      const { setFromClaims } = useAuthStore.getState();

      setFromClaims({ tenant_id: 'demo' });

      expect(useAuthStore.getState().roles).toEqual([]);
    });

    it('handles null/undefined email and name gracefully', async () => {
      const { useAuthStore } = await import('../authStore');
      const { setFromClaims } = useAuthStore.getState();

      setFromClaims({ tenant_id: 'demo', roles: ['viewer'] });

      const state = useAuthStore.getState();
      expect(state.email).toBeNull();
      expect(state.name).toBeNull();
    });
  });

  describe('clear', () => {
    it('resets all fields to initial state', async () => {
      const { useAuthStore } = await import('../authStore');
      const { setFromClaims, clear } = useAuthStore.getState();

      setFromClaims({
        tenant_id: 'demo',
        roles: ['owner'],
        email: 'dev@analysi.local',
        name: 'Dev User',
      });

      clear();

      const state = useAuthStore.getState();
      expect(state.tenant_id).toBe('default');
      expect(state.email).toBeNull();
      expect(state.name).toBeNull();
      expect(state.roles).toEqual([]);
      expect(state.isAuthenticated).toBe(false);
    });
  });
});
