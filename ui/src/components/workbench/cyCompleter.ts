/**
 * Cy Language Completer for Ace Editor
 *
 * Provides intelligent autocompletion for Cy language based on actual .cy file syntax:
 * - Keywords: if, elif, else, return, null, True, False, and, or, not
 * - Built-in functions: input, len, str, store_artifact, llm_run
 * - Operators: =, ==, !=, ??, +, -, *, /, <, >, <=, >=
 * - Integration tools: app::integration::action(...)
 * - Native tools (fetched from MCP)
 * - String interpolation: ${variable}
 * - Comments: # comment
 */

import type { Ace } from 'ace-builds';

// MCP tool summary type (from cy-script-assistant)
export interface ToolSummary {
  fqn: string; // Fully qualified name (e.g., "llm_run" or "app::virustotal::ip_reputation")
  name?: string;
  description?: string;
  integration_id?: string | null;
  params_schema?: {
    type: string;
    properties?: Record<string, unknown>;
    required?: string[];
  };
}

// Integration summary type
export interface IntegrationSummary {
  id: string; // e.g., "splunk", "virustotal"
  name: string;
  description?: string;
  archetypes?: string[]; // e.g., ["SIEM", "ThreatIntel"]
}

// Cache for tool completions
let toolsCache: ToolSummary[] = [];
let integrationsCache: IntegrationSummary[] = [];

/**
 * Set tools cache (called from Workbench when MCP tools are fetched)
 */
export function setCyToolsCache(tools: ToolSummary[]): void {
  toolsCache = tools;
}

/**
 * Get current tools cache
 */
export function getCyToolsCache(): ToolSummary[] {
  return toolsCache;
}

/**
 * Set integrations cache (called from Workbench when integrations are fetched)
 */
export function setCyIntegrationsCache(integrations: IntegrationSummary[]): void {
  integrationsCache = integrations;
}

/**
 * Get current integrations cache
 */
export function getCyIntegrationsCache(): IntegrationSummary[] {
  return integrationsCache;
}

/**
 * Cy language keywords
 */
const CY_KEYWORDS: Ace.Completion[] = [
  {
    caption: 'if',
    value: 'if',
    meta: 'keyword',
    score: 1000,
    docHTML:
      '<b>if</b><br/>Conditional statement<br/>Example: <code>if (value != null) { ... }</code>',
  },
  {
    caption: 'elif',
    value: 'elif',
    meta: 'keyword',
    score: 1000,
    docHTML:
      '<b>elif</b><br/>Else-if conditional<br/>Example: <code>elif (count > 5) { ... }</code>',
  },
  {
    caption: 'else',
    value: 'else',
    meta: 'keyword',
    score: 1000,
    docHTML: '<b>else</b><br/>Else clause<br/>Example: <code>else { ... }</code>',
  },
  {
    caption: 'return',
    value: 'return',
    meta: 'keyword',
    score: 1000,
    docHTML:
      '<b>return</b><br/>Return a value from the script<br/>Example: <code>return alert</code>',
  },
  {
    caption: 'null',
    value: 'null',
    meta: 'constant',
    score: 900,
    docHTML: '<b>null</b><br/>Null value',
  },
  {
    caption: 'True',
    value: 'True',
    meta: 'constant',
    score: 900,
    docHTML: '<b>True</b><br/>Boolean true constant',
  },
  {
    caption: 'False',
    value: 'False',
    meta: 'constant',
    score: 900,
    docHTML: '<b>False</b><br/>Boolean false constant',
  },
  {
    caption: 'and',
    value: 'and',
    meta: 'operator',
    score: 850,
    docHTML: '<b>and</b><br/>Logical AND operator',
  },
  {
    caption: 'or',
    value: 'or',
    meta: 'operator',
    score: 850,
    docHTML: '<b>or</b><br/>Logical OR operator',
  },
  {
    caption: 'not',
    value: 'not',
    meta: 'operator',
    score: 850,
    docHTML: '<b>not</b><br/>Logical NOT operator',
  },
];

/**
 * Built-in Cy functions and variables
 */
const CY_BUILT_INS: Ace.Completion[] = [
  // Special variables
  {
    caption: 'input',
    value: 'input',
    meta: 'variable',
    score: 1100,
    docHTML:
      '<b>input</b><br/>Input data passed to the script (typically an alert object)<br/>Example: <code>alert = input</code>',
  },

  // Built-in functions
  {
    caption: 'len',
    snippet: 'len(${1:value})',
    meta: 'function',
    score: 950,
    docHTML:
      '<b>len(value)</b><br/>Get length of a list, dict, or string<br/>Example: <code>count = len(events)</code>',
  },
  {
    caption: 'str',
    snippet: 'str(${1:value})',
    meta: 'function',
    score: 950,
    docHTML:
      '<b>str(value)</b><br/>Convert value to string<br/>Example: <code>target_ip = str(alert.observables[0].value)</code>',
  },
  // Operators
  {
    caption: '??',
    value: ' ?? ',
    meta: 'operator',
    score: 900,
    docHTML:
      '<b>??</b><br/>Null-coalescing operator - returns right side if left is null<br/>Example: <code>value = data["field"] ?? "default"</code>',
  },
];

/**
 * Common Cy code snippets based on actual .cy files
 */
const CY_SNIPPETS: Ace.Completion[] = [
  {
    caption: 'alert-enrichment',
    snippet:
      '# ${1:Task Name} (Alert Enrichment)\n# ${2:Task description}\n\n# Get the alert from input\nalert = input\n\n# Initialize enrichments\nenrichments = alert["enrichments"] ?? {}\n\n# TODO: Add enrichment logic here\n\n# Add enrichment data\nenrichments["${3:enrichment_key}"] = {\n    "data_source": "${4:source}",\n    ${5:# enrichment fields}\n}\nalert["enrichments"] = enrichments\n\n# Return the enriched alert\nreturn alert',
    meta: 'snippet',
    score: 1200,
    docHTML: '<b>Alert Enrichment Template</b><br/>Standard pattern for alert enrichment tasks',
  },
  {
    caption: 'if-null-check',
    snippet:
      'if (${1:value} != null) {\n    ${2:# handle non-null}\n} else {\n    ${3:# handle null}\n}',
    meta: 'snippet',
    score: 950,
    docHTML: '<b>If null check</b><br/>Check if value is not null',
  },
  {
    caption: 'safe-dict-access',
    snippet: '${1:value} = ${2:dict}["${3:key}"] ?? ${4:default}',
    meta: 'snippet',
    score: 950,
    docHTML:
      '<b>Safe dictionary access</b><br/>Access dictionary with default fallback using ?? operator',
  },
  {
    caption: 'string-interpolation',
    snippet: '"${1:text} \\${${2:variable}}"',
    meta: 'snippet',
    score: 900,
    docHTML: '<b>String interpolation</b><br/>Embed variables in strings using ${...}',
  },
];

/**
 * Build a snippet argument for a single parameter, respecting its type.
 * Strings get quotes, numbers/booleans/objects/arrays don't.
 * Uses the schema default value when available.
 */
function buildSnippetArg(
  name: string,
  tabstop: number,
  prop: { type?: string; default?: unknown }
): string {
  const defaultVal = prop.default;
  const placeholder =
    defaultVal !== undefined && typeof defaultVal !== 'object'
      ? String(defaultVal as string | number | boolean)
      : name;
  const type = prop.type || 'string';

  if (type === 'string') {
    return `${name}="\${${tabstop}:${placeholder}}"`;
  }
  // Numbers, booleans, objects, arrays — no quotes
  return `${name}=\${${tabstop}:${placeholder}}`;
}

/**
 * Build a snippet string from params_schema.
 * Required params come first, then optional. Each gets a tabstop.
 * Falls back to ${1:params} if no schema properties.
 */
function buildSnippetFromSchema(fqn: string, schema?: ToolSummary['params_schema']): string {
  const props = schema?.properties;
  if (!props || Object.keys(props).length === 0) {
    return `${fqn}(\${1:params})`;
  }

  const requiredSet = new Set(schema?.required ?? []);
  const requiredParams = Object.keys(props).filter((k) => requiredSet.has(k));
  const optionalParams = Object.keys(props).filter((k) => !requiredSet.has(k));
  const ordered = [...requiredParams, ...optionalParams];

  const args = ordered
    .map((name, i) =>
      buildSnippetArg(name, i + 1, props[name] as { type?: string; default?: unknown })
    )
    .join(', ');
  return `${fqn}(${args})`;
}

/**
 * Build docHTML with parameter table from params_schema.
 */
function buildDocHTML(
  fqn: string,
  description: string | undefined,
  toolType: string,
  schema?: ToolSummary['params_schema']
): string {
  let html = `<b>${fqn}</b>`;
  if (description) {
    html += `<br/>${description}`;
  }

  const props = schema?.properties;
  if (props && Object.keys(props).length > 0) {
    const requiredSet = new Set(schema?.required ?? []);
    html += '<br/><b>Parameters:</b>';
    for (const [name, rawProp] of Object.entries(props)) {
      const prop = rawProp as { type?: string; description?: string };
      const typeName = prop.type || 'any';
      const req = requiredSet.has(name) ? ', required' : '';
      const desc = prop.description ? ` - ${prop.description}` : '';
      html += `<br/>&bull; <b>${name}</b> (${typeName}${req})${desc}`;
    }
  }

  html += `<br/><i>${toolType}</i>`;
  return html;
}

/**
 * Extract the short name from a tool FQN.
 * "native::llm::llm_run" -> "llm_run"
 * "app::virustotal::ip_reputation" -> "ip_reputation"
 * "sum" -> "sum"
 */
function getShortName(fqn: string): string {
  const parts = fqn.split('::');
  return parts[parts.length - 1];
}

/**
 * Get the name used in Cy scripts for a tool.
 * Native tools use short names (e.g., "llm_run"), integration tools use FQN (e.g., "app::virustotal::ip_reputation").
 */
function getCyName(fqn: string): string {
  if (fqn.startsWith('native::')) {
    return getShortName(fqn);
  }
  return fqn;
}

/**
 * Convert tool summaries to Ace completions
 */
function toolsToCompletions(tools: ToolSummary[]): Ace.Completion[] {
  return tools.map((tool) => {
    const isIntegration = tool.fqn.startsWith('app::');
    const isNative = tool.fqn.startsWith('native::');
    const meta = isIntegration ? 'integration' : 'tool';
    // Native tools score higher than snippets (950) so they appear first
    const score = isIntegration ? 880 : 1000;
    const toolType = isIntegration ? 'Integration tool' : 'Native tool';
    const cyName = getCyName(tool.fqn);

    return {
      caption: isNative ? cyName : tool.fqn,
      snippet: buildSnippetFromSchema(cyName, tool.params_schema),
      meta,
      score,
      docHTML: buildDocHTML(tool.fqn, tool.description, toolType, tool.params_schema),
    };
  });
}

/**
 * Match prefix against native tools by short name (e.g., "llm_run" or "store_art").
 */
function findNativeToolCompletions(
  prefix: string
): { completions: Ace.Completion[]; filterAll: boolean } | null {
  if (!prefix || prefix.length < 2) return null;
  const lowerPrefix = prefix.toLowerCase();
  const nativeTools = toolsCache.filter(
    (t) => t.fqn.startsWith('native::') && getShortName(t.fqn).toLowerCase().includes(lowerPrefix)
  );
  if (nativeTools.length === 0) return null;
  return {
    completions: [...toolsToCompletions(nativeTools), ...CY_BUILT_INS, ...CY_KEYWORDS],
    filterAll: false,
  };
}

/**
 * Build completions for the "app::" prefix — integrations + their tools.
 */
function buildAppCompletions(): Ace.Completion[] {
  const integrationCompletions = integrationsCache.map(
    (integration): Ace.Completion & { command?: string } => ({
      caption: `app::${integration.id}::`,
      value: `app::${integration.id}::`,
      meta: 'integration',
      score: 1100,
      command: 'startAutocomplete',
      docHTML: integration.description
        ? `<b>${integration.name}</b><br/>${integration.description}`
        : `<b>${integration.name}</b>`,
    })
  );
  const integrationToolCompletions = toolsToCompletions(
    toolsCache.filter((t) => t.fqn.startsWith('app::'))
  );
  return [...integrationCompletions, ...integrationToolCompletions];
}

/**
 * Get context-aware completions based on cursor position
 */
function getContextCompletions(
  session: Ace.EditSession,
  pos: Ace.Point,
  prefix: string
): {
  completions: Ace.Completion[];
  filterAll: boolean;
} {
  const line = session.getLine(pos.row);
  const beforeCursor = line.substring(0, pos.column);

  // Check if we're typing a comment
  if (beforeCursor.trimStart().startsWith('#')) {
    return { completions: [], filterAll: true }; // Don't show completions in comments
  }

  // Progressive integration autocomplete
  // Case 2: User is typing "app::integration_id::" - show tools for that integration
  // Check this FIRST because it's more specific
  const integrationToolPattern = /\bapp::(\w+)::(\w*)$/;
  const integrationToolMatch = integrationToolPattern.exec(beforeCursor);
  if (integrationToolMatch) {
    const integrationId = integrationToolMatch[1];
    // Filter tools that belong to this integration
    const integrationTools = toolsCache.filter((t) => t.fqn.startsWith(`app::${integrationId}::`));

    // Only return tool completions if we found tools for this integration
    // Otherwise fall through to show integrations (in case they mistyped)
    if (integrationTools.length > 0) {
      return {
        completions: toolsToCompletions(integrationTools),
        filterAll: false,
      };
    }
  }

  // Case 1: User is typing "app::" or "app::partial" - show all active integrations
  // Also include integration tools so they survive Ace's local filter as the user
  // continues typing. Ace caches the initial getCompletions result and locally filters
  // on subsequent keystrokes — if we only return integrations here, tools never appear
  // when the prefix narrows to "app::integration::".
  const appPattern = /\bapp::(\w*)$/;
  const appMatch = appPattern.exec(beforeCursor);
  if (appMatch) {
    return { completions: buildAppCompletions(), filterAll: false };
  }

  // Check if we're typing an integration tool (contains app::) - fallback for general case
  // Require "app::" (not just "app") to avoid live autocomplete re-triggering on short prefixes
  if (beforeCursor.includes('app::')) {
    const integrationTools = toolsCache.filter((t) => t.fqn.startsWith('app::'));
    return {
      completions: toolsToCompletions(integrationTools),
      filterAll: false,
    };
  }

  // Check if prefix matches a native tool by short name (e.g., typing "llm_run" or "store_art")
  const nativeToolCompletions = findNativeToolCompletions(prefix);
  if (nativeToolCompletions) {
    return nativeToolCompletions;
  }

  // Generic namespace handling (e.g., "str::", "list::", etc.)
  if (prefix && prefix.includes('::')) {
    const matchingTools = toolsCache.filter((t) => t.fqn.startsWith(prefix));
    if (matchingTools.length > 0) {
      return { completions: toolsToCompletions(matchingTools), filterAll: false };
    }
  }

  // Check if we're at the start of a line (show snippets with higher priority)
  if (beforeCursor.trim() === '' || beforeCursor.trim() === prefix) {
    // Include native tools from cache (with full params_schema) alongside built-ins
    const nativeToolCompletions = toolsToCompletions(
      toolsCache.filter((t) => t.fqn.startsWith('native::'))
    );
    return {
      completions: [...CY_SNIPPETS, ...CY_KEYWORDS, ...nativeToolCompletions, ...CY_BUILT_INS],
      filterAll: false,
    };
  }

  // After 'return' keyword, suggest common values
  if (/\breturn\s*$/.test(beforeCursor)) {
    return {
      completions: [
        {
          caption: 'alert',
          value: 'alert',
          meta: 'variable',
          score: 1000,
          docHTML: '<b>alert</b><br/>Return the enriched alert (common pattern)',
        },
      ],
      filterAll: false,
    };
  }

  return { completions: [], filterAll: false };
}

/**
 * Main Cy language completer
 */
export const cyCompleter: Ace.Completer = {
  identifierRegexps: [/[a-zA-Z_0-9:]+/], // Include : for app:: patterns

  getCompletions: (
    _editor: Ace.Editor,
    session: Ace.EditSession,
    pos: Ace.Point,
    prefix: string,
    callback: Ace.CompleterCallback
  ) => {
    try {
      // Get context-specific completions
      const { completions: contextCompletions, filterAll } = getContextCompletions(
        session,
        pos,
        prefix
      );

      if (filterAll) {
        // Context says no completions (e.g., in a comment)
        callback(null, []);
        return;
      }

      let allCompletions: Ace.Completion[];

      // If we have context-specific completions, use ONLY those (don't merge with others)
      if (contextCompletions.length > 0) {
        allCompletions = contextCompletions;
      } else {
        // No context-specific completions, show all available completions
        const toolCompletions = toolsToCompletions(toolsCache);
        allCompletions = [...CY_KEYWORDS, ...CY_BUILT_INS, ...CY_SNIPPETS, ...toolCompletions];
      }

      // Filter by prefix if provided
      if (prefix && prefix.length > 0) {
        const lowerPrefix = prefix.toLowerCase();
        allCompletions = allCompletions.filter(
          (c) =>
            (c.caption && c.caption.toLowerCase().includes(lowerPrefix)) ||
            (c.value && c.value.toLowerCase().includes(lowerPrefix))
        );
      }

      // Remove duplicates by caption
      const seen = new Set<string>();
      allCompletions = allCompletions.filter((c) => {
        const captionKey = c.caption || '';
        if (seen.has(captionKey)) {
          return false;
        }
        seen.add(captionKey);
        return true;
      });

      // Sort by score (highest first)
      allCompletions.sort((a, b) => (b.score || 0) - (a.score || 0));

      callback(null, allCompletions);
    } catch (error) {
      console.error('Cy completer error:', error);
      // Return at least built-ins on error
      callback(null, [...CY_KEYWORDS, ...CY_BUILT_INS]);
    }
  },

  getDocTooltip: (item: Ace.Completion) => {
    if (!item.docHTML && item.caption) {
      item.docHTML = `<b>${item.caption}</b>`;
    }
  },
};
