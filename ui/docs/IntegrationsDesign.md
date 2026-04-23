# Integrations Design

## Overview

The integrations system is a **registry-driven, dynamically-rendered integration management platform** that enables users to configure, monitor, and execute various third-party service integrations without requiring custom UI code for each integration type.

## Core Architecture Decisions

### 1. Registry-Driven Dynamic UI Architecture

**Decision**: Use a backend registry API that provides JSON schemas to dynamically generate all UI forms and configurations.

**Rationale**:
- **Maintainability**: New integrations can be added purely through backend changes
- **Consistency**: All integrations follow the same UX patterns and setup flow
- **Single Source of Truth**: Integration definitions live exclusively in the backend
- **Type Safety**: JSON schemas provide validation rules and type information

**Implementation**:
- The backend registry API (`/integrations/registry`) returns complete schemas for:
  - `settings_schema`: Configuration fields (host, port, etc.)
  - `credential_schema`: Authentication fields (username/password, API keys)
  - `connector schemas`: Parameters and schedules for each connector
  - Display metadata: Names, descriptions, placeholders, validation patterns

### 2. No Custom Integration Components

**Decision**: Avoid creating integration-specific UI components. Use a single, generic `IntegrationSetupWizard` that adapts to any integration type.

**Trade-offs**:
- ✅ **Pros**:
  - Zero frontend changes needed for new integrations
  - Consistent experience across all integration types
  - Reduced code complexity and maintenance burden
- ❌ **Cons**:
  - Cannot provide highly specialized UIs for complex integrations
  - Limited to what JSON schema can express
  - Visual uniformity might not be ideal for all use cases

## Component Architecture

### IntegrationSetupWizard

A multi-step wizard that guides users through integration setup:

```typescript
type WizardStep = 'integration' | 'credentials' | 'schedules' | 'summary';
```

**Features**:
- **Dynamic Form Generation**: Automatically creates form fields from JSON schemas
- **Progressive Disclosure**: Shows only relevant steps based on integration requirements
- **Real-time Validation**: Applies schema-defined validation rules
- **Progress Tracking**: Visual feedback during setup process
- **Unsaved Changes Protection**: Confirmation dialog before losing data

### Integrations page

The main page component (`ui/src/pages/Integrations.tsx`) managing:
- Available integrations sidebar
- User's configured integration cards
- Integration details modal
- Connector execution and monitoring

## State Management Patterns

### 1. Polling Controllers with Maps

**Problem**: Multiple connectors can run simultaneously, each needing independent polling.

**Solution**: Use Maps to track multiple polling controllers:
```typescript
const modalPollingControllers = useRef<Map<string, PollingController>>(new Map());
const cardPollingControllers = useRef<Map<string, PollingController>>(new Map());
```

**Key**: `${integrationId}-${connector}` ensures unique tracking per connector.

### 2. Running State Tracking

```typescript
const [runningConnectors, setRunningConnectors] = useState<Map<string, string>>(new Map());
// Map of integrationId+connector -> runId
```

This prevents duplicate runs and provides accurate spinner states.

## UI/UX Patterns

### 1. Multi-Step Wizard Flow

1. **Integration Settings**: Configure base integration (host, port, etc.)
2. **Credentials**: Add one or more credential sets
3. **Schedules**: Configure connector schedules with parameters
4. **Summary**: Review and execute setup with progress tracking

### 2. Connector Management

**Multiple Connector Support**:
- Integration cards show dropdown menu when multiple connectors available
- Details modal lists all connectors with individual run buttons
- Each connector tracks its own running state independently

**Visual Feedback**:
- Spinning icons for running connectors
- Color-coded status badges (succeeded, failed, running, pending)
- Duration calculation and display (when timestamps available)

### 3. Security Patterns

**Credential Handling**:
- Passwords/tokens redacted by default with `••••••••`
- Eye icon toggles for revealing sensitive values
- Per-field visibility tracking to prevent accidental exposure
- Sensitive field detection via pattern matching:
  ```typescript
  /password|secret|api[_-]?key|token|credential|private[_-]?key|auth/i
  ```

### 4. Error Handling

**Validation Errors**:
- Inline field-level error messages
- Schema-driven validation (required, pattern, min/max)
- User-friendly error message formatting from backend validation errors

**Confirmation Dialogs**:
- Unsaved changes warning
- Delete confirmation with alternative actions (disable vs delete)
- Custom modal dialogs instead of browser `window.confirm()`

## API Integration Patterns

### 1. Combined Credential Creation

Using the new combined endpoint:
```typescript
POST /integrations/{id}/credentials
{
  "provider": "splunk",
  "account": "integration-id",
  "secret": { /* credential fields */ },
  "is_primary": true,
  "purpose": "admin"
}
```

### 2. Dynamic Parameter Handling

Schedules derive their parameters from the action's `params_schema`.
When an action updates its schema, the UI picks up the new fields on
the next registry fetch and the generic form renders whatever is
declared — there is no UI change needed.

### 3. Health and Status Monitoring

```typescript
// Parallel fetching for efficiency
const integrationsWithHealth = await Promise.all(
  integrations.map(async (integration) => {
    const health = await backendApi.getIntegrationHealth(integration.integration_id);
    const lastRun = await backendApi.getIntegrationRuns(integration.integration_id, { limit: 1 });
    return { ...integration, health_status: health.status, last_run_at: lastRun?.completed_at };
  })
);
```

## Event Handling Patterns

### 1. Escape Key Management

```typescript
// Proper event capture with stale closure prevention
useEffect(() => {
  const handleEscape = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      // Handle in priority order: dropdowns -> modals -> forms
    }
  };
  document.addEventListener('keydown', handleEscape, true); // capture phase
  return () => document.removeEventListener('keydown', handleEscape, true);
}, [/* all state dependencies */]);
```

### 2. Click Outside Detection

For dropdown menus and modals:
```typescript
const handleClickOutside = (event: MouseEvent) => {
  if (showConnectorMenu) {
    const target = event.target as HTMLElement;
    if (!target.closest('[data-connector-menu]')) {
      setShowConnectorMenu(null);
    }
  }
};
```

## Design Trade-offs

1. **Generic UI only** — cannot provide highly specialized experiences for
   complex integrations. All integrations render through the same
   schema-driven form and card surfaces.
2. **Schema constraints** — UI expressiveness is limited to what JSON
   Schema can describe.
3. **No integration-specific validation** — business rules that cannot be
   expressed as schema rules have no UI hook.

## Page Layout

### Left Sidebar - Available Integrations
- Always visible integration type list
- Quick-add buttons for each type
- Connector count indicators
- Search/filter capabilities (future)

### Main Content - Integration Cards Grid
- Responsive grid layout (1-4 columns based on screen size)
- Each card shows:
  - Integration name and type
  - Health status indicator
  - Enable/disable toggle
  - Last run information
  - Quick actions (View Details, Run, Delete)
  - Connector dropdown for multiple connectors

### Modals

#### Setup Wizard Modal
- Multi-step form with progress indicator
- Step navigation (back/next)
- Validation before proceeding
- Final progress tracking during setup

#### Details Modal
- Full configuration display with redacted secrets
- Complete connector list with individual controls
- Run history table with expandable details
- Schedule management (future)

## Testing Considerations

### Integration Tests
- `run_integration_tests.sh` covers:
  - Registry API responses
  - Integration CRUD operations
  - Credential creation with combined endpoint
  - Connector run triggering
  - 409 duplicate prevention

### Frontend Testing Needs
- Schema-to-form generation
- Validation rule application
- Polling lifecycle management
- Error state handling

## Security Considerations

1. **No Credentials in Frontend State**: Only redacted values stored
2. **Explicit Reveal Actions**: User must click to see sensitive data
3. **Secure Transmission**: All credentials sent over HTTPS
4. **No Credential Persistence**: No localStorage/sessionStorage for secrets
5. **Audit Trail**: All integration actions logged in backend

## Performance Optimizations

1. **Lazy Loading**: Integration details fetched on-demand
2. **Pagination**: Run history limited to recent entries
3. **Debounced Updates**: Prevent rapid state changes during polling
4. **Cleanup on Unmount**: All polling controllers properly terminated
5. **Memoization**: Expensive computations cached with useCallback/useMemo

## Development Guidelines

### Adding New Integration Types

1. Define integration in backend registry
2. No frontend changes required
3. Test with existing UI components
4. Verify schema validation rules

### Modifying UI Behavior

1. Changes affect ALL integrations
2. Test with multiple integration types
3. Ensure backward compatibility
4. Update this documentation

### Debugging Tips

1. Check browser console for schema validation errors
2. Verify backend registry response format
3. Monitor network tab for polling requests
4. Use React DevTools to inspect state changes

## Conclusion

The integrations system is a fully dynamic, registry-driven UI that prioritizes maintainability and consistency over customization. New integration types can be added through backend manifest changes alone while preserving a unified user experience.