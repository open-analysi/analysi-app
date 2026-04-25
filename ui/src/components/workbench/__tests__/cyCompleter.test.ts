import type { Ace } from 'ace-builds';
import { describe, it, expect, beforeEach } from 'vitest';

import {
  cyCompleter,
  setCyToolsCache,
  setCyIntegrationsCache,
  type ToolSummary,
  type IntegrationSummary,
} from '../cyCompleter';

// Mock Ace types
const createMockSession = (line: string): Ace.EditSession => {
  return {
    getLine: () => line,
  } as unknown as Ace.EditSession;
};

const createMockPosition = (column: number): Ace.Point => {
  return {
    row: 0,
    column,
  } as Ace.Point;
};

describe('cyCompleter', () => {
  // Test constants
  const VIRUSTOTAL_PREFIX = 'app::virustotal::';
  const SPLUNK_PREFIX = 'app::splunk::';
  const ABUSEIPDB_PREFIX = 'app::abuseipdb::';
  const VT_IP_REPUTATION = 'app::virustotal::ip_reputation';
  const VT_DOMAIN_REPUTATION = 'app::virustotal::domain_reputation';
  const SPLUNK_SPL_RUN = 'app::splunk::spl_run';

  const mockIntegrations: IntegrationSummary[] = [
    { id: 'virustotal', name: 'VirusTotal', description: 'Threat intelligence' },
    { id: 'splunk', name: 'Splunk', description: 'SIEM platform' },
    { id: 'abuseipdb', name: 'AbuseIPDB', description: 'IP reputation' },
  ];

  const mockTools: ToolSummary[] = [
    {
      fqn: VT_IP_REPUTATION,
      name: 'IP Reputation',
      description: 'Check IP reputation',
      integration_id: 'virustotal',
      params_schema: {
        type: 'object',
        properties: {
          ip: { type: 'string', description: 'IP address to check' },
          extended: { type: 'boolean', description: 'Include extended info' },
        },
        required: ['ip'],
      },
    },
    {
      fqn: VT_DOMAIN_REPUTATION,
      name: 'Domain Reputation',
      description: 'Check domain reputation',
      integration_id: 'virustotal',
    },
    {
      fqn: SPLUNK_SPL_RUN,
      name: 'Run SPL Query',
      description: 'Execute Splunk SPL query',
      integration_id: 'splunk',
      params_schema: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'SPL query string' },
          earliest_time: { type: 'string', description: 'Start time' },
          latest_time: { type: 'string', description: 'End time' },
        },
        required: ['query'],
      },
    },
    {
      fqn: 'app::abuseipdb::lookup_ip',
      name: 'Lookup IP',
      description: 'Lookup IP in AbuseIPDB',
      integration_id: 'abuseipdb',
    },
    {
      fqn: 'native::llm::llm_run',
      name: 'LLM Run',
      description: 'Execute LLM prompts',
      integration_id: null,
      params_schema: {
        type: 'object',
        properties: {
          prompt: { type: 'string', description: 'The prompt text' },
          model: { type: 'string', description: 'Model to use' },
        },
        required: ['prompt'],
      },
    },
    {
      fqn: 'native::tools::store_artifact',
      name: 'Store Artifact',
      description: 'Store investigation artifacts',
      integration_id: null,
      params_schema: {
        type: 'object',
        properties: {
          name: { type: 'string', description: 'Artifact name' },
          artifact: { type: 'string', description: 'Artifact data' },
        },
        required: ['name', 'artifact'],
      },
    },
  ];

  beforeEach(() => {
    setCyIntegrationsCache(mockIntegrations);
    setCyToolsCache(mockTools);
  });

  it('should show integrations when typing "app::"', async () => {
    const line = 'app::';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, '', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();
        // Should include integrations (sorted first by score 1100) AND tools (score 880)
        const integrationEntries = completions?.filter((c) => c.caption?.endsWith('::'));
        expect(integrationEntries?.length).toBe(3);
        expect(integrationEntries?.map((c) => c.caption)).toEqual([
          VIRUSTOTAL_PREFIX,
          SPLUNK_PREFIX,
          ABUSEIPDB_PREFIX,
        ]);
        // Tools are also included so they survive Ace's local filter
        const toolEntries = completions?.filter(
          (c) => c.caption?.startsWith('app::') && !c.caption?.endsWith('::')
        );
        expect(toolEntries?.length).toBeGreaterThan(0);
        resolve();
      });
    });
  });

  it('should show integrations when typing "app::v" (partial integration name)', async () => {
    const line = 'app::v';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, 'v', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();
        // Should show integrations filtered by prefix 'v'
        const filtered = completions?.filter((c) =>
          c.caption?.toLowerCase().includes('v'.toLowerCase())
        );
        expect(filtered?.some((c) => c.caption === VIRUSTOTAL_PREFIX)).toBe(true);
        resolve();
      });
    });
  });

  it('should show virustotal tools when typing "app::virustotal::"', async () => {
    const line = VIRUSTOTAL_PREFIX;
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, '', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();

        // Should return only virustotal tools
        expect(completions?.length).toBe(2); // 2 virustotal tools
        expect(completions?.map((c) => c.caption)).toContain(VT_IP_REPUTATION);
        expect(completions?.map((c) => c.caption)).toContain(VT_DOMAIN_REPUTATION);
        expect(completions?.every((c) => c.meta === 'integration' || c.meta === 'tool')).toBe(true);
        resolve();
      });
    });
  });

  it('should show splunk tools when typing "app::splunk::"', async () => {
    const line = SPLUNK_PREFIX;
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, '', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();

        // Should return only splunk tools
        expect(completions?.length).toBe(1); // 1 splunk tool
        expect(completions?.map((c) => c.caption)).toContain(SPLUNK_SPL_RUN);
        resolve();
      });
    });
  });

  it('should include integration tools alongside integrations when typing "app::"', async () => {
    // Ace caches completions from the initial getCompletions call and locally filters
    // as the user types more. If only integrations are returned for "app::", tools never
    // appear when the prefix narrows to "app::splunk::" because Ace never re-calls
    // getCompletions. So tools MUST be included in the "app::" response.
    const line = 'app::';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, 'app::', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();

        // Should include both integrations AND integration tools
        const integrationEntries = completions?.filter((c) => c.caption?.endsWith('::'));
        const toolEntries = completions?.filter(
          (c) => c.caption?.startsWith('app::') && !c.caption?.endsWith('::')
        );

        expect(integrationEntries?.length).toBeGreaterThan(0);
        // Tools MUST be present alongside integrations so they survive
        // Ace's local filter when the prefix narrows to "app::splunk::"
        expect(toolEntries?.length).toBeGreaterThan(0);
        expect(completions?.some((c) => c.caption === SPLUNK_SPL_RUN)).toBe(true);
        expect(completions?.some((c) => c.caption === VT_IP_REPUTATION)).toBe(true);
        resolve();
      });
    });
  });

  it('should not show completions in comments', async () => {
    const line = '# app::';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, 'app::', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toEqual([]);
        resolve();
      });
    });
  });

  it('should show keywords at start of line', async () => {
    const line = 'if';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, 'if', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();
        expect(completions?.some((c) => c.caption === 'if')).toBe(true);
        expect(completions?.some((c) => c.caption === 'elif')).toBe(true);
        resolve();
      });
    });
  });

  it('should show built-in functions when typing "llm"', async () => {
    const line = 'result = llm';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, 'llm', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();
        expect(completions?.some((c) => c.caption === 'llm_run')).toBe(true);
        const llmRun = completions?.find((c) => c.caption === 'llm_run');
        // Native tool from cache takes precedence over hardcoded built-in
        expect(llmRun?.meta).toBe('tool');
        expect(llmRun?.snippet).toContain('llm_run');
        resolve();
      });
    });
  });

  it('should show "alert" after "return" keyword', async () => {
    const line = 'return ';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, '', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();
        expect(completions?.some((c) => c.caption === 'alert')).toBe(true);
        resolve();
      });
    });
  });

  it('should show integrations even for nonexistent integration typed', async () => {
    const line = 'app::nonexistent::';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, '', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();
        // Should fall back to showing integrations since no tools found
        expect(completions?.some((c) => c.meta === 'integration')).toBe(true);
        resolve();
      });
    });
  });

  it('should include tool descriptions in completions', async () => {
    const line = VIRUSTOTAL_PREFIX;
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, '', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();
        const ipReputationTool = completions?.find((c) => c.caption === VT_IP_REPUTATION);
        expect(ipReputationTool).toBeDefined();
        expect(ipReputationTool?.docHTML).toContain('Check IP reputation');
        resolve();
      });
    });
  });

  it('should handle empty caches gracefully', async () => {
    // Temporarily clear caches
    setCyIntegrationsCache([]);
    setCyToolsCache([]);

    const line = 'app::';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, '', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();
        // With empty integration cache, should return empty array for context-specific completions
        // But will show 0 integrations (correct fallback behavior)
        expect(completions?.filter((c) => c.meta === 'integration').length).toBe(0);

        // Restore caches for other tests
        setCyIntegrationsCache(mockIntegrations);
        setCyToolsCache(mockTools);
        resolve();
      });
    });
  });

  it('should show snippets for empty line', async () => {
    const line = '';
    const session = createMockSession(line);
    const pos = createMockPosition(0);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, '', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();
        // Should include snippets like alert-enrichment
        expect(completions?.some((c) => c.meta === 'snippet')).toBe(true);
        expect(completions?.some((c) => c.caption === 'alert-enrichment')).toBe(true);
        resolve();
      });
    });
  });

  it('should generate named parameter snippets from params_schema', async () => {
    const line = VIRUSTOTAL_PREFIX;
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, '', (err, completions) => {
        expect(err).toBeNull();
        const tool = completions?.find((c) => c.caption === VT_IP_REPUTATION);
        expect(tool?.snippet).toBeDefined();
        // Required param 'ip' should come first (tabstop 1), optional 'extended' second (tabstop 2)
        // String params get quotes, boolean params don't
        expect(tool?.snippet).toContain('ip="${1:ip}"');
        expect(tool?.snippet).toContain('extended=${2:extended}');
        expect(tool?.snippet).toBe(
          'app::virustotal::ip_reputation(ip="${1:ip}", extended=${2:extended})'
        );
        resolve();
      });
    });
  });

  it('should fallback to ${1:params} when no params_schema', async () => {
    const line = VIRUSTOTAL_PREFIX;
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, '', (err, completions) => {
        expect(err).toBeNull();
        const tool = completions?.find((c) => c.caption === VT_DOMAIN_REPUTATION);
        expect(tool?.snippet).toBe('app::virustotal::domain_reputation(${1:params})');
        resolve();
      });
    });
  });

  it('should show parameter details in docHTML', async () => {
    const line = VIRUSTOTAL_PREFIX;
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, '', (err, completions) => {
        expect(err).toBeNull();
        const tool = completions?.find((c) => c.caption === VT_IP_REPUTATION);
        expect(tool?.docHTML).toContain('<b>Parameters:</b>');
        expect(tool?.docHTML).toContain('<b>ip</b> (string, required) - IP address to check');
        expect(tool?.docHTML).toContain('<b>extended</b> (boolean) - Include extended info');
        resolve();
      });
    });
  });

  it('should match native tools by short name when typing "llm_run"', async () => {
    const line = 'result = llm_run';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, 'llm_run', (err, completions) => {
        expect(err).toBeNull();
        expect(completions).toBeDefined();
        // Should find native::llm::llm_run via short name matching
        const llmRun = completions?.find((c) => c.caption === 'llm_run');
        expect(llmRun).toBeDefined();
        expect(llmRun?.meta).toBe('tool');
        // Snippet should use short name (Cy syntax), not FQN
        expect(llmRun?.snippet).toContain('llm_run(');
        expect(llmRun?.snippet).toContain('prompt=');
        // Should NOT contain 'native::' in snippet
        expect(llmRun?.snippet).not.toContain('native::');
        resolve();
      });
    });
  });

  it('should match native tools by partial short name', async () => {
    const line = 'result = store_art';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions(
        {} as Ace.Editor,
        session,
        pos,
        'store_art',
        (err, completions) => {
          expect(err).toBeNull();
          expect(completions).toBeDefined();
          const storeArtifact = completions?.find((c) => c.caption === 'store_artifact');
          expect(storeArtifact).toBeDefined();
          expect(storeArtifact?.snippet).toContain('store_artifact(');
          expect(storeArtifact?.snippet).not.toContain('native::');
          resolve();
        }
      );
    });
  });

  it('should use short name with params_schema for native tool snippet', async () => {
    const line = 'result = llm_run';
    const session = createMockSession(line);
    const pos = createMockPosition(line.length);

    return new Promise<void>((resolve) => {
      cyCompleter.getCompletions({} as Ace.Editor, session, pos, 'llm_run', (err, completions) => {
        expect(err).toBeNull();
        const llmRun = completions?.find((c) => c.caption === 'llm_run');
        expect(llmRun?.snippet).toBe('llm_run(prompt="${1:prompt}", model="${2:model}")');
        resolve();
      });
    });
  });
});
