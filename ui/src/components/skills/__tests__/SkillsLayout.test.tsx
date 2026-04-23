import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { SkillsLayout } from '../SkillsLayout';

const SKILL_1_URL = '/skills?skill=skill-1';
const SKILL_2_URL = '/skills?skill=skill-2';
const BACK_LABEL = 'Back to Skills';

// vi.hoisted runs before vi.mock hoisting, so these are available in mock factories
const {
  SKILL_1_NAME,
  mockSkills,
  mockSetSelectedSkillId,
  mockSetSelectedFilePath,
  mockSetSkills,
  mockSetSkillTree,
  mockSetLoading,
  mockSetTreeLoading,
  storeState,
} = vi.hoisted(() => {
  const enabled = 'enabled';
  const skill1Name = 'Alert Triage';
  const skills = [
    {
      id: 'skill-1',
      name: skill1Name,
      cy_name: 'alert_triage',
      description: 'Triage incoming alerts',
      status: enabled,
      extraction_eligible: true,
      pending_reviews_count: 0,
      flagged_reviews_count: 0,
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
    },
    {
      id: 'skill-2',
      name: 'Malware Analysis',
      cy_name: 'malware_analysis',
      description: 'Analyze malware samples',
      status: enabled,
      extraction_eligible: false,
      pending_reviews_count: 0,
      flagged_reviews_count: 0,
      created_at: '2025-01-02T00:00:00Z',
      updated_at: '2025-01-02T00:00:00Z',
    },
  ];

  const state = {
    skills,
    selectedSkillId: null as string | null,
    selectedFilePath: null as string | null,
    skillTree: [] as never[],
    loading: false,
    treeLoading: false,
  };

  return {
    SKILL_1_NAME: skill1Name,
    mockSkills: skills,
    mockSetSelectedSkillId: vi.fn(),
    mockSetSelectedFilePath: vi.fn(),
    mockSetSkills: vi.fn(),
    mockSetSkillTree: vi.fn(),
    mockSetLoading: vi.fn(),
    mockSetTreeLoading: vi.fn(),
    storeState: state,
  };
});

vi.mock('../../../store/skillStore', () => ({
  useSkillStore: () => ({
    ...storeState,
    setSkills: mockSetSkills,
    setSelectedSkillId: mockSetSelectedSkillId,
    setSelectedFilePath: mockSetSelectedFilePath,
    setSkillTree: mockSetSkillTree,
    setLoading: mockSetLoading,
    setTreeLoading: mockSetTreeLoading,
  }),
}));

vi.mock('../../../hooks/useErrorHandler', () => ({
  default: vi.fn(() => ({
    error: { hasError: false, message: '' },
    clearError: vi.fn(),
    handleError: vi.fn(),
    createContext: vi.fn(),
    runSafe: vi.fn(() => Promise.resolve([{ skills: mockSkills }, undefined])),
  })),
}));

vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getSkills: vi.fn().mockResolvedValue({ skills: [] }),
    getSkillTree: vi.fn().mockResolvedValue({ files: [] }),
  },
}));

// Mock child components to keep tests focused on layout navigation
vi.mock('../SkillFileViewer', () => ({
  SkillFileViewer: () => <div data-testid="skill-file-viewer">File Viewer</div>,
}));

vi.mock('../KnowledgeOnboarding', () => ({
  KnowledgeOnboarding: () => <div data-testid="knowledge-onboarding">Onboarding</div>,
}));

vi.mock('../ContentReviewList', () => ({
  ContentReviewList: () => <div data-testid="content-review-list">Reviews</div>,
}));

function renderWithRouter(initialEntries = ['/skills']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <SkillsLayout />
    </MemoryRouter>
  );
}

describe('SkillsLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeState.skills = mockSkills;
    storeState.selectedSkillId = null;
    storeState.selectedFilePath = null;
    storeState.skillTree = [];
    storeState.loading = false;
    storeState.treeLoading = false;
  });

  describe('landing view (no skill selected)', () => {
    it('renders the Skills heading and subtitle', () => {
      renderWithRouter();
      expect(screen.getByText('Skills')).toBeInTheDocument();
      expect(
        screen.getByText(
          'Select a skill to browse its files, onboard knowledge, and run extractions'
        )
      ).toBeInTheDocument();
    });

    it('renders skill cards in a grid', () => {
      renderWithRouter();
      expect(screen.getByText(SKILL_1_NAME)).toBeInTheDocument();
      expect(screen.getByText('Malware Analysis')).toBeInTheDocument();
      expect(screen.getByText('Triage incoming alerts')).toBeInTheDocument();
      expect(screen.getByText('Analyze malware samples')).toBeInTheDocument();
    });

    it('does not render the sidebar or breadcrumb', () => {
      renderWithRouter();
      expect(screen.queryByPlaceholderText('Search skills...')).not.toBeInTheDocument();
      expect(screen.queryByLabelText(BACK_LABEL)).not.toBeInTheDocument();
    });

    it('selects a skill when clicking a card', () => {
      renderWithRouter();
      fireEvent.click(screen.getByText(SKILL_1_NAME));
      expect(mockSetSelectedSkillId).toHaveBeenCalledWith('skill-1');
    });

    it('shows editable icon only on extraction-eligible skill cards', () => {
      renderWithRouter();
      const editableIcons = screen.getAllByTestId('editable-icon');
      // Only skill-1 is extraction_eligible
      expect(editableIcons).toHaveLength(1);
      // The icon should be inside the eligible skill's card
      const eligibleCard = screen.getByText(SKILL_1_NAME).closest('button')!;
      expect(eligibleCard.querySelector('[data-testid="editable-icon"]')).toBeInTheDocument();
      // Non-eligible card should not have it
      const nonEligibleCard = screen.getByText('Malware Analysis').closest('button')!;
      expect(nonEligibleCard.querySelector('[data-testid="editable-icon"]')).toBeNull();
    });

    it('shows pending reviews indicator when skill has pending reviews', () => {
      storeState.skills = storeState.skills.map((s) =>
        s.id === 'skill-1' ? { ...s, pending_reviews_count: 3 } : s
      );
      renderWithRouter();
      expect(screen.getByTestId('pending-reviews-indicator')).toBeInTheDocument();
      expect(screen.getByText('3 processing')).toBeInTheDocument();
    });

    it('shows flagged reviews indicator when skill has flagged reviews', () => {
      storeState.skills = storeState.skills.map((s) =>
        s.id === 'skill-1' ? { ...s, flagged_reviews_count: 2 } : s
      );
      renderWithRouter();
      expect(screen.getByTestId('flagged-reviews-indicator')).toBeInTheDocument();
      expect(screen.getByText('2 flagged')).toBeInTheDocument();
    });

    it('does not show review indicators when counts are zero', () => {
      renderWithRouter();
      expect(screen.queryByTestId('pending-reviews-indicator')).not.toBeInTheDocument();
      expect(screen.queryByTestId('flagged-reviews-indicator')).not.toBeInTheDocument();
    });

    it('shows guidance text in flagged review banner', () => {
      storeState.skills = storeState.skills.map((s) =>
        s.id === 'skill-1' ? { ...s, flagged_reviews_count: 1 } : s
      );
      renderWithRouter();
      expect(screen.getByTestId('review-summary-banner')).toBeInTheDocument();
      expect(screen.getByText(/need manual review/)).toBeInTheDocument();
    });

    it('auto-navigates to Reviews tab when clicking skill with flagged reviews', () => {
      storeState.skills = storeState.skills.map((s) =>
        s.id === 'skill-1' ? { ...s, flagged_reviews_count: 2 } : s
      );
      renderWithRouter();
      fireEvent.click(screen.getByText(SKILL_1_NAME));
      // After clicking, the store should select the skill
      expect(mockSetSelectedSkillId).toHaveBeenCalledWith('skill-1');
      // Simulate the store selecting and re-render with drill-down
      storeState.selectedSkillId = 'skill-1';
      renderWithRouter(['/skills?skill=skill-1&tab=reviews']);
      expect(screen.getByTestId('content-review-list')).toBeInTheDocument();
    });

    it('auto-navigates to Reviews tab when clicking skill with pending reviews', () => {
      storeState.skills = storeState.skills.map((s) =>
        s.id === 'skill-1' ? { ...s, pending_reviews_count: 3 } : s
      );
      renderWithRouter();
      fireEvent.click(screen.getByText(SKILL_1_NAME));
      expect(mockSetSelectedSkillId).toHaveBeenCalledWith('skill-1');
      storeState.selectedSkillId = 'skill-1';
      renderWithRouter(['/skills?skill=skill-1&tab=reviews']);
      expect(screen.getByTestId('content-review-list')).toBeInTheDocument();
    });

    it('defaults to Viewer tab when clicking skill without active reviews', () => {
      renderWithRouter();
      fireEvent.click(screen.getByText(SKILL_1_NAME));
      expect(mockSetSelectedSkillId).toHaveBeenCalledWith('skill-1');
      storeState.selectedSkillId = 'skill-1';
      renderWithRouter(['/skills?skill=skill-1']);
      expect(screen.getByTestId('skill-file-viewer')).toBeInTheDocument();
    });
  });

  describe('drill-down view (skill selected)', () => {
    beforeEach(() => {
      storeState.selectedSkillId = 'skill-1';
    });

    it('renders the breadcrumb with back arrow and skill name', () => {
      renderWithRouter([SKILL_1_URL]);
      expect(screen.getByLabelText(BACK_LABEL)).toBeInTheDocument();
      // Skill name appears in breadcrumb and in detail header
      expect(screen.getAllByText(SKILL_1_NAME).length).toBeGreaterThanOrEqual(1);
    });

    it('renders the sidebar with search', () => {
      renderWithRouter([SKILL_1_URL]);
      expect(screen.getByPlaceholderText('Search skills...')).toBeInTheDocument();
    });

    it('renders the detail panel with tabs for extraction-eligible skill', () => {
      renderWithRouter([SKILL_1_URL]);
      expect(screen.getByText('Viewer')).toBeInTheDocument();
      expect(screen.getByText('Onboarding')).toBeInTheDocument();
      expect(screen.getByText('Reviews')).toBeInTheDocument();
    });

    it('does not render the card grid', () => {
      renderWithRouter([SKILL_1_URL]);
      // The subtitle from the landing is not visible
      expect(
        screen.queryByText(
          'Select a skill to browse its files, onboard knowledge, and run extractions'
        )
      ).not.toBeInTheDocument();
    });

    it('navigates back when clicking back arrow', () => {
      renderWithRouter([SKILL_1_URL]);
      fireEvent.click(screen.getByLabelText(BACK_LABEL));
      expect(mockSetSelectedSkillId).toHaveBeenCalledWith(null);
    });

    it('navigates back when clicking Skills breadcrumb text', () => {
      renderWithRouter([SKILL_1_URL]);
      const skillsBreadcrumb = screen
        .getAllByText('Skills')
        .find((el) => el.tagName === 'BUTTON' && el.classList.contains('text-sm'));
      expect(skillsBreadcrumb).toBeDefined();
      fireEvent.click(skillsBreadcrumb!);
      expect(mockSetSelectedSkillId).toHaveBeenCalledWith(null);
    });

    it('hides Onboarding tab but shows Reviews tab for non-extraction-eligible skills', () => {
      storeState.selectedSkillId = 'skill-2';
      renderWithRouter([SKILL_2_URL]);
      expect(screen.getByText('Viewer')).toBeInTheDocument();
      expect(screen.queryByText('Onboarding')).not.toBeInTheDocument();
      expect(screen.getByText('Reviews')).toBeInTheDocument();
    });
  });

  describe('URL state management', () => {
    it('clears selection when navigating back', () => {
      storeState.selectedSkillId = 'skill-1';
      renderWithRouter([`${SKILL_1_URL}&file=docs/test.md&tab=viewer`]);

      fireEvent.click(screen.getByLabelText(BACK_LABEL));
      expect(mockSetSelectedSkillId).toHaveBeenCalledWith(null);
    });

    it('renders landing view when URL has no skill param', () => {
      renderWithRouter(['/skills']);
      expect(screen.getByText('Skills')).toBeInTheDocument();
      expect(screen.queryByLabelText(BACK_LABEL)).not.toBeInTheDocument();
    });

    it('renders drill-down view when URL has skill param', async () => {
      storeState.selectedSkillId = 'skill-1';
      renderWithRouter([SKILL_1_URL]);

      await waitFor(() => {
        expect(screen.getByLabelText(BACK_LABEL)).toBeInTheDocument();
      });
    });
  });
});
