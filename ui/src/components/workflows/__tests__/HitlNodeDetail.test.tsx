import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { renderHitlDetail } from '../WorkflowExecutionReaflow';

describe('renderHitlDetail', () => {
  it('renders HITL panel when node is paused with valid HITL JSON', () => {
    const hitlPayload = {
      hitl: true,
      question: 'Should we escalate this alert?',
      channel: 'slack-security',
      options: 'Yes, No, Need more info',
    };
    const result = renderHitlDetail('paused', JSON.stringify(hitlPayload));
    const { container } = render(<>{result}</>);

    expect(screen.getByText('Waiting for Human Response')).toBeInTheDocument();
    expect(screen.getByText('Should we escalate this alert?')).toBeInTheDocument();
    expect(screen.getByText('Channel: slack-security')).toBeInTheDocument();
    expect(screen.getByText('Yes')).toBeInTheDocument();
    expect(screen.getByText('No')).toBeInTheDocument();
    expect(screen.getByText('Need more info')).toBeInTheDocument();
    // Should not show error display
    expect(container.querySelector('.node-detail-error')).not.toBeInTheDocument();
  });

  it('renders HITL panel without options when none are provided', () => {
    const hitlPayload = {
      hitl: true,
      question: 'Approve this action?',
    };
    const result = renderHitlDetail('paused', JSON.stringify(hitlPayload));
    render(<>{result}</>);

    expect(screen.getByText('Waiting for Human Response')).toBeInTheDocument();
    expect(screen.getByText('Approve this action?')).toBeInTheDocument();
    expect(screen.queryByText('Channel:')).not.toBeInTheDocument();
  });

  it('returns null for paused node with non-JSON error_message', () => {
    const result = renderHitlDetail('paused', 'plain text error message');
    expect(result).toBeNull();
  });

  it('returns null for paused node with JSON that has hitl=false', () => {
    const result = renderHitlDetail('paused', JSON.stringify({ hitl: false, question: 'hi' }));
    expect(result).toBeNull();
  });

  it('returns null for paused node with JSON that is missing hitl field', () => {
    const result = renderHitlDetail('paused', JSON.stringify({ question: 'hi' }));
    expect(result).toBeNull();
  });

  it('returns null when status is not paused', () => {
    const hitlPayload = JSON.stringify({ hitl: true, question: 'test' });
    expect(renderHitlDetail('running', hitlPayload)).toBeNull();
    expect(renderHitlDetail('failed', hitlPayload)).toBeNull();
    expect(renderHitlDetail('completed', hitlPayload)).toBeNull();
  });

  it('returns null when error_message is undefined', () => {
    expect(renderHitlDetail('paused', undefined)).toBeNull();
  });

  it('handles options with extra whitespace and empty entries', () => {
    const hitlPayload = {
      hitl: true,
      question: 'Pick one',
      options: '  Yes ,, No , ',
    };
    const result = renderHitlDetail('paused', JSON.stringify(hitlPayload));
    render(<>{result}</>);

    expect(screen.getByText('Yes')).toBeInTheDocument();
    expect(screen.getByText('No')).toBeInTheDocument();
    // Empty strings from ",," and trailing "," should be filtered out
    const optionElements = screen.getAllByText(/^(Yes|No)$/);
    expect(optionElements).toHaveLength(2);
  });
});
