import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    importSkill: vi.fn(),
  },
}));

import { backendApi } from '../../../services/backendApi';
import { SkillImportModal } from '../SkillImportModal';

const TEST_ZIP_NAME = 'test.zip';
const ZIP_MIME = 'application/zip';
const FILE_INPUT_ID = 'import-file-input';
const mockOnClose = vi.fn();
const mockOnImported = vi.fn();

async function renderModal(isOpen = true) {
  const result = render(
    <SkillImportModal isOpen={isOpen} onClose={mockOnClose} onImported={mockOnImported} />
  );
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  return result;
}

async function uploadFile() {
  const file = new File(['content'], TEST_ZIP_NAME, { type: ZIP_MIME });
  const input = screen.getByTestId(FILE_INPUT_ID);
  await act(async () => {
    fireEvent.change(input, { target: { files: [file] } });
    await new Promise((r) => setTimeout(r, 0));
  });
}

describe('SkillImportModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the modal when open', async () => {
    await renderModal();
    expect(screen.getByText('Import Skill')).toBeInTheDocument();
    expect(screen.getByTestId('import-dropzone')).toBeInTheDocument();
  });

  it('does not render content when closed', async () => {
    await renderModal(false);
    expect(screen.queryByText('Import Skill')).not.toBeInTheDocument();
  });

  it('shows success state after import', async () => {
    vi.mocked(backendApi.importSkill).mockResolvedValue({
      skill_id: 'skill-123',
      name: 'Test Skill',
      documents_submitted: 3,
      review_ids: ['r1', 'r2', 'r3'],
    });

    await renderModal();
    await uploadFile();

    await waitFor(() => {
      expect(screen.getByText('Import successful')).toBeInTheDocument();
    });

    expect(screen.getByText(/Test Skill/)).toBeInTheDocument();
    expect(screen.getByText(/3 documents submitted/)).toBeInTheDocument();
    expect(screen.getByText('Go to Skill')).toBeInTheDocument();
  });

  it('shows sync failures when present', async () => {
    vi.mocked(backendApi.importSkill).mockResolvedValue({
      skill_id: 'skill-123',
      name: 'Test Skill',
      documents_submitted: 2,
      review_ids: ['r1'],
      sync_failures: [{ file: 'bad.md', error: 'schema mismatch' }],
    });

    await renderModal();
    await uploadFile();

    await waitFor(() => {
      expect(screen.getByText('Sync failures')).toBeInTheDocument();
    });
  });

  it('calls onImported when Go to Skill is clicked', async () => {
    vi.mocked(backendApi.importSkill).mockResolvedValue({
      skill_id: 'skill-456',
      name: 'My Skill',
      documents_submitted: 1,
      review_ids: ['r1'],
    });

    await renderModal();
    await uploadFile();

    await waitFor(() => {
      expect(screen.getByText('Go to Skill')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText('Go to Skill'));
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(mockOnImported).toHaveBeenCalledWith('skill-456');
    expect(mockOnClose).toHaveBeenCalled();
  });

  it('renders ProblemDetail title, detail, and hint from backend', async () => {
    const axiosError = Object.assign(new Error('422'), {
      response: {
        status: 422,
        data: {
          title: 'Missing SKILL.md',
          detail: 'Every skill package needs a SKILL.md file at the root.',
          hint: 'Add a SKILL.md file and re-export the package.',
          error_code: 'missing_skill_md',
        },
      },
    });
    vi.mocked(backendApi.importSkill).mockRejectedValue(axiosError);

    await renderModal();
    await uploadFile();

    await waitFor(() => {
      expect(screen.getByText('Missing SKILL.md')).toBeInTheDocument();
    });
    expect(
      screen.getByText('Every skill package needs a SKILL.md file at the root.')
    ).toBeInTheDocument();
    expect(screen.getByText('How to fix')).toBeInTheDocument();
    expect(screen.getByText('Add a SKILL.md file and re-export the package.')).toBeInTheDocument();
  });

  it('renders ProblemDetail without hint when hint is absent', async () => {
    const axiosError = Object.assign(new Error('409'), {
      response: {
        status: 409,
        data: {
          title: 'Skill already exists',
          detail: 'A skill with name "Alert Triage" already exists.',
          error_code: 'skill_already_exists',
        },
      },
    });
    vi.mocked(backendApi.importSkill).mockRejectedValue(axiosError);

    await renderModal();
    await uploadFile();

    await waitFor(() => {
      expect(screen.getByText('Skill already exists')).toBeInTheDocument();
    });
    expect(screen.getByText(/Alert Triage/)).toBeInTheDocument();
    expect(screen.queryByText('How to fix')).not.toBeInTheDocument();
  });

  it('falls back to error message when response has no ProblemDetail', async () => {
    vi.mocked(backendApi.importSkill).mockRejectedValue(new Error('Network error'));

    await renderModal();
    await uploadFile();

    await waitFor(() => {
      expect(screen.getByText('Import failed')).toBeInTheDocument();
    });
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('shows Try Again button on error and resets to dropzone', async () => {
    vi.mocked(backendApi.importSkill).mockRejectedValue(new Error('Network error'));

    await renderModal();
    await uploadFile();

    await waitFor(() => {
      expect(screen.getByText('Import failed')).toBeInTheDocument();
    });

    expect(screen.getByText('Try Again')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByText('Try Again'));
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(screen.getByTestId('import-dropzone')).toBeInTheDocument();
    expect(screen.queryByText('Import failed')).not.toBeInTheDocument();
  });
});
