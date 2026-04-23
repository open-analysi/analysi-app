import { render } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

import { AuditTrailPage } from '../AuditTrail';

// Mock the necessary components but don't rely on testIds
vi.mock('../../components/settings/AuditTrailView', () => ({
  AuditTrailView: () => <div>Audit Trail View Content</div>,
}));

vi.mock('../../components/settings/ConfigurationHistory', () => ({
  ConfigurationHistory: () => <div>Configuration History Content</div>,
}));

describe('AuditTrailPage', () => {
  it('renders the audit trail page', () => {
    const { container } = render(<AuditTrailPage />);

    // Just check if the component renders without being empty
    expect(container).not.toBeEmptyDOMElement();
  });
});
