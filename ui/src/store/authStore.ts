import { create } from 'zustand';

export interface AuthState {
  /** Tenant ID extracted from the JWT `tenant_id` claim. */
  tenant_id: string;
  email: string | null;
  name: string | null;
  roles: string[];
  isAuthenticated: boolean;
  /** Raw OIDC access token for API requests. */
  accessToken: string | null;
  setFromClaims: (claims: Record<string, unknown>, accessToken?: string) => void;
  clear: () => void;
}

const initialState = {
  tenant_id: 'default',
  email: null,
  name: null,
  roles: [] as string[],
  isAuthenticated: false,
  accessToken: null as string | null,
};

export const useAuthStore = create<AuthState>((set) => ({
  ...initialState,

  setFromClaims: (claims, accessToken) =>
    set({
      tenant_id: (claims.tenant_id as string) || 'default',
      email: (claims.email as string) || null,
      name: (claims.name as string) || null,
      roles: Array.isArray(claims.roles) ? (claims.roles as string[]) : [],
      isAuthenticated: true,
      accessToken: accessToken ?? null,
    }),

  clear: () => set({ ...initialState }),
}));
