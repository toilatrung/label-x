import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ContextBar } from '@/components/layout/ContextBar';

const setDatasetId = vi.fn();
let datasetIds: number[] = [1, 2, 3];
vi.mock('@/lib/auth/auth-context', () => ({
  useAuth: () => ({
    user: { id: 2, role: 'qa_lead', fullName: 'QA' },
    session: { roles: datasetIds.map((dataset_id) => ({ role: 'qa_lead', dataset_id })) },
    datasetId: 2,
    setDatasetId,
  }),
}));

beforeEach(() => { setDatasetId.mockClear(); datasetIds = [1, 2, 3]; });

describe('ContextBar dataset menu', () => {
  it('opens with focus on the current dataset and supports ArrowDown/ArrowUp/Home/End', async () => {
    render(<ContextBar />);
    const trigger = screen.getByRole('button', { name: /Dataset/ });
    fireEvent.click(trigger);
    expect(screen.getByRole('menu')).toBeDefined();
    const items = screen.getAllByRole('menuitem');
    await waitFor(() => expect(document.activeElement).toBe(items[1]));
    fireEvent.keyDown(items[1], { key: 'ArrowDown' });
    expect(document.activeElement).toBe(items[2]);
    fireEvent.keyDown(items[2], { key: 'ArrowDown' });
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(items[0], { key: 'End' });
    expect(document.activeElement).toBe(items[2]);
    fireEvent.keyDown(items[2], { key: 'Home' });
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(items[0], { key: 'ArrowUp' });
    expect(document.activeElement).toBe(items[2]);
  });

  it('opens with ArrowDown on the trigger, picks a dataset and closes', async () => {
    render(<ContextBar />);
    const trigger = screen.getByRole('button', { name: /Dataset/ });
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    expect(screen.getByRole('menu')).toBeDefined();
    await waitFor(() => expect(document.activeElement).toBe(screen.getAllByRole('menuitem')[1]));
    fireEvent.click(screen.getAllByRole('menuitem')[2]);
    expect(setDatasetId).toHaveBeenCalledWith(3);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('closes on Escape and returns focus to the trigger, and on an outside pointer', () => {
    render(<ContextBar />);
    const trigger = screen.getByRole('button', { name: /Dataset/ });
    fireEvent.click(trigger);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    expect(document.activeElement).toBe(trigger);
    fireEvent.click(trigger);
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('renders a static chip when the session has a single dataset', () => {
    datasetIds = [2];
    render(<ContextBar />);
    expect(screen.queryByRole('button', { name: /Dataset/ })).toBeNull();
    expect(screen.getByText('Dataset')).toBeDefined();
  });
});
