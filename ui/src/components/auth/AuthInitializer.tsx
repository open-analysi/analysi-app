import React, { useEffect } from 'react';

import { OidcUserStatus, useOidcAccessToken, useOidcUser } from '@axa-fr/react-oidc';

import { useAuthStore } from '../../store/authStore';

/** Custom claims we expect in the access token from Keycloak */
interface AccessTokenClaims {
  tenant_id?: string;
  roles?: string[];
  email?: string;
  name?: string;
}

/** OIDC user profile fields we read (standard + custom) */
interface OidcUserProfile {
  email?: string;
  name?: string;
}

/**
 * AuthInitializer
 *
 * Syncs the authenticated OIDC user's claims to the authStore.
 * Must be rendered inside OidcProvider.
 *
 * - Reads custom claims (tenant_id, roles) from the access token payload
 * - Reads profile info (email, name) from the OIDC user info
 * - Writes to authStore so the rest of the app can access user context
 *   without importing @axa-fr/react-oidc
 */
const AuthInitializer: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { oidcUser, oidcUserLoadingState } = useOidcUser() as {
    oidcUser: OidcUserProfile | null;
    oidcUserLoadingState: OidcUserStatus;
  };
  const { accessToken, accessTokenPayload } = useOidcAccessToken() as {
    accessToken: string | null;
    accessTokenPayload: AccessTokenClaims | null;
  };
  const { setFromClaims, clear } = useAuthStore();

  // Only depend on oidcUserLoadingState (a string enum value) to avoid infinite
  // loops from object identity changes in accessTokenPayload/oidcUser between renders.
  // All values are read from the current closure when the state actually transitions.
  useEffect(() => {
    if (oidcUserLoadingState === OidcUserStatus.Loaded && accessTokenPayload) {
      setFromClaims(
        {
          tenant_id: accessTokenPayload.tenant_id,
          roles: accessTokenPayload.roles,
          email: oidcUser?.email ?? accessTokenPayload.email,
          name: oidcUser?.name ?? accessTokenPayload.name,
        },
        accessToken ?? undefined,
      );
    } else if (oidcUserLoadingState === OidcUserStatus.Unauthenticated) {
      clear();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [oidcUserLoadingState]);

  return <>{children}</>;
};

export default AuthInitializer;
