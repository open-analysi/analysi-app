/**
 * Custom hook that fetches integration and tool data for Cy editor autocomplete.
 * Extracted from WorkbenchModern.tsx to reduce file size and lint errors.
 */
import { useEffect } from 'react';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import type { IntegrationTypeInfo } from '../../types/integration';

import { setCyIntegrationsCache, setCyToolsCache } from './cyCompleter';
import type { ToolSummaryInternal } from './workbenchUtils';

/**
 * Fetches configured integrations, their tools, and native tools on mount,
 * then populates the Cy completer caches for autocomplete suggestions.
 */
export function useAutocompleteData(): void {
  const { runSafe } = useErrorHandler('useAutocompleteData');

  useEffect(() => {
    const fetchAutoCompleteData = async () => {
      try {
        // STEP 1: Fetch configured integrations to determine which types are active
        const [configuredIntegrations] = await runSafe<Array<{ integration_type: string }>>(
          backendApi.getIntegrations({ enabled: true }) as Promise<
            Array<{ integration_type: string }>
          >,
          'getIntegrations',
          { action: 'loading configured integrations for autocomplete' }
        );

        if (!configuredIntegrations) {
          console.warn('[Autocomplete] Failed to fetch configured integrations');
          setCyIntegrationsCache([]);
          setCyToolsCache([]);
          return;
        }

        const activeTypes = new Set(configuredIntegrations.map((int) => int.integration_type));

        // STEP 2: Fetch integration types from registry
        const [integrationTypes] = await runSafe(
          backendApi.getIntegrationTypes(),
          'getIntegrationTypes',
          { action: 'loading integration types for autocomplete' }
        );

        if (!integrationTypes) {
          console.warn('[Autocomplete] Failed to fetch integration types');
          setCyIntegrationsCache([]);
          setCyToolsCache([]);
          return;
        }

        // STEP 3: Filter to only show integration types that have active instances
        const activeIntegrationTypes = integrationTypes.filter((intType) =>
          activeTypes.has(intType.integration_type)
        );

        // STEP 4: Transform to the format expected by cyCompleter
        const integrationSummaries = activeIntegrationTypes.map((intType) => ({
          id: intType.integration_type,
          name: intType.display_name || intType.integration_type,
          description: intType.description,
        }));

        setCyIntegrationsCache(integrationSummaries);

        // STEP 5: Fetch detailed information for each active integration type to get tools
        const allTools: ToolSummaryInternal[] = [];
        await Promise.all(
          activeIntegrationTypes.map(async (intType) => {
            try {
              const [detailedIntType] = await runSafe<IntegrationTypeInfo>(
                backendApi.getIntegrationType(intType.integration_type),
                'getIntegrationType',
                {
                  action: 'loading integration actions for autocomplete',
                  entityId: intType.integration_type,
                }
              );

              if (detailedIntType?.actions && Array.isArray(detailedIntType.actions)) {
                for (const action of detailedIntType.actions) {
                  allTools.push({
                    fqn: `app::${intType.integration_type}::${action.action_id}`,
                    name: action.name,
                    description: action.description,
                    integration_id: intType.integration_type,
                    params_schema: action.params_schema as ToolSummaryInternal['params_schema'],
                  });
                }
              }
            } catch (err) {
              console.error(
                `[Autocomplete] Failed to fetch tools for ${intType.integration_type}:`,
                err
              );
            }
          })
        );

        // STEP 6: Fetch all tools from the all-tools endpoint and merge
        try {
          const [allToolsResponse] = await runSafe(backendApi.getAllTools(), 'getAllTools', {
            action: 'loading all tools for autocomplete',
          });
          const typed = allToolsResponse as { tools?: ToolSummaryInternal[] } | undefined;
          if (typed?.tools) {
            const existingFqns = new Set(allTools.map((t) => t.fqn));
            for (const tool of typed.tools) {
              if (!existingFqns.has(tool.fqn) && !tool.fqn.startsWith('app::')) {
                allTools.push({
                  fqn: tool.fqn,
                  name: tool.name,
                  description: tool.description,
                  integration_id: tool.integration_id ?? '',
                  params_schema: tool.params_schema,
                });
              }
            }
          }
        } catch (err) {
          console.warn(
            '[Autocomplete] Failed to fetch tools, continuing with integration tools only:',
            err
          );
        }

        setCyToolsCache(allTools);
        // Log unique tool namespaces for debugging
        const namespaces = new Set(allTools.map((t) => t.fqn.split('::').slice(0, -1).join('::')));
        console.info(
          '[Autocomplete] Loaded',
          integrationSummaries.length,
          'integrations and',
          allTools.length,
          'tools. Namespaces:',
          [...namespaces].sort((a, b) => a.localeCompare(b))
        );
      } catch (err) {
        console.error('[Autocomplete] Failed to fetch autocomplete data:', err);
        setCyIntegrationsCache([]);
        setCyToolsCache([]);
      }
    };

    void fetchAutoCompleteData();
  }, [runSafe]);
}
