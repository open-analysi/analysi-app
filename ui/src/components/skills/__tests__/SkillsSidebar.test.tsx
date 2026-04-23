import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

import { Skill, SkillFile } from '../../../types/skill';
import { SkillsSidebar } from '../SkillsSidebar';

const mockSkills: Skill[] = [
  {
    id: 'skill-1',
    name: 'Alert Triage',
    cy_name: 'alert_triage',
    description: 'Triage incoming alerts',
    status: 'enabled',
    extraction_eligible: true,
    pending_reviews_count: 0,
    flagged_reviews_count: 0,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    version: '1.0',
    visible: true,
    system_only: false,
    app: 'default',
    namespace: 'skills',
    tenant_id: 'test-tenant',
    module_type: 'skill',
    root_document_path: '/docs',
    config: {},
  },
  {
    id: 'skill-2',
    name: 'Malware Analysis',
    cy_name: 'malware_analysis',
    description: 'Analyze malware samples',
    status: 'enabled',
    extraction_eligible: false,
    pending_reviews_count: 0,
    flagged_reviews_count: 0,
    created_at: '2025-01-02T00:00:00Z',
    updated_at: '2025-01-02T00:00:00Z',
    version: '1.0',
    visible: true,
    system_only: false,
    app: 'default',
    namespace: 'skills',
    tenant_id: 'test-tenant',
    module_type: 'skill',
    root_document_path: '/docs',
    config: {},
  },
];

const mockFiles: SkillFile[] = [
  { path: 'docs/overview.md', document_id: 'doc-1', staged: false },
  { path: 'docs/staged-file.md', document_id: 'doc-2', staged: true },
];

describe('SkillsSidebar', () => {
  const defaultProps = {
    skills: mockSkills,
    selectedSkillId: null,
    selectedFilePath: null,
    skillTree: [],
    onSelectSkill: vi.fn(),
    onSelectFile: vi.fn(),
  };

  it('renders all skills', () => {
    render(<SkillsSidebar {...defaultProps} />);
    expect(screen.getByText('Alert Triage')).toBeInTheDocument();
    expect(screen.getByText('Malware Analysis')).toBeInTheDocument();
  });

  it('filters skills by search term', () => {
    render(<SkillsSidebar {...defaultProps} />);
    const searchInput = screen.getByPlaceholderText('Search skills...');
    fireEvent.change(searchInput, { target: { value: 'malware' } });

    expect(screen.queryByText('Alert Triage')).not.toBeInTheDocument();
    expect(screen.getByText('Malware Analysis')).toBeInTheDocument();
  });

  it('shows empty state when no skills match search', () => {
    render(<SkillsSidebar {...defaultProps} />);
    const searchInput = screen.getByPlaceholderText('Search skills...');
    fireEvent.change(searchInput, { target: { value: 'nonexistent' } });

    expect(screen.getByText('No skills match your search')).toBeInTheDocument();
  });

  it('calls onSelectSkill when clicking a skill', () => {
    const onSelectSkill = vi.fn();
    render(<SkillsSidebar {...defaultProps} onSelectSkill={onSelectSkill} />);

    fireEvent.click(screen.getByText('Alert Triage'));
    expect(onSelectSkill).toHaveBeenCalledWith('skill-1');
  });

  it('shows file tree when skill is selected', () => {
    render(<SkillsSidebar {...defaultProps} selectedSkillId="skill-1" skillTree={mockFiles} />);

    expect(screen.getByText('overview.md')).toBeInTheDocument();
    expect(screen.getByText('staged-file.md')).toBeInTheDocument();
  });

  it('calls onSelectFile when clicking a file', () => {
    const onSelectFile = vi.fn();
    render(
      <SkillsSidebar
        {...defaultProps}
        selectedSkillId="skill-1"
        skillTree={mockFiles}
        onSelectFile={onSelectFile}
      />
    );

    fireEvent.click(screen.getByText('overview.md'));
    expect(onSelectFile).toHaveBeenCalledWith('docs/overview.md');
  });
});
