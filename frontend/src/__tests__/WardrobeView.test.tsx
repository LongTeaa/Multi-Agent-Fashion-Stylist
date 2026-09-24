import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WardrobeView } from '@/components/wardrobe/WardrobeView';

vi.mock('@/components/wardrobe/WardrobeInventory', () => ({
  WardrobeInventory: ({ onSwitchToIngestion }: { onSwitchToIngestion?: () => void }) => (
    <div data-testid="mock-inventory">
      <span>Mock Inventory Content</span>
      <button data-testid="trigger-ingestion" onClick={onSwitchToIngestion}>
        Add Garment
      </button>
    </div>
  ),
}));

vi.mock('@/components/ingestion/IngestionWorkflow', () => ({
  IngestionWorkflow: ({ onFinish }: { onFinish?: () => void }) => (
    <div data-testid="mock-ingestion">
      <span>Mock Ingestion Content</span>
      <button data-testid="trigger-finish" onClick={onFinish}>
        Complete Ingestion
      </button>
    </div>
  ),
}));

describe('WardrobeView Component', () => {
  it('renders WardrobeInventory by default', () => {
    render(<WardrobeView />);

    expect(screen.getByTestId('mock-inventory')).toBeDefined();
    expect(screen.queryByTestId('mock-ingestion')).toBeNull();
  });

  it('switches to IngestionWorkflow when onSwitchToIngestion is triggered', () => {
    render(<WardrobeView />);

    fireEvent.click(screen.getByTestId('trigger-ingestion'));

    expect(screen.queryByTestId('mock-inventory')).toBeNull();
    expect(screen.getByTestId('mock-ingestion')).toBeDefined();
    expect(screen.getByTestId('btn-back-to-inventory')).toBeDefined();
    expect(screen.getByText('Quay lại tủ đồ')).toBeDefined();
  });

  it('returns to WardrobeInventory when back button is clicked', () => {
    render(<WardrobeView />);

    // Switch to ingestion
    fireEvent.click(screen.getByTestId('trigger-ingestion'));
    expect(screen.getByTestId('mock-ingestion')).toBeDefined();

    // Click back button
    fireEvent.click(screen.getByTestId('btn-back-to-inventory'));
    expect(screen.getByTestId('mock-inventory')).toBeDefined();
    expect(screen.queryByTestId('mock-ingestion')).toBeNull();
  });

  it('returns to WardrobeInventory when ingestion completes', () => {
    render(<WardrobeView />);

    // Switch to ingestion
    fireEvent.click(screen.getByTestId('trigger-ingestion'));
    expect(screen.getByTestId('mock-ingestion')).toBeDefined();

    // Complete ingestion
    fireEvent.click(screen.getByTestId('trigger-finish'));
    expect(screen.getByTestId('mock-inventory')).toBeDefined();
    expect(screen.queryByTestId('mock-ingestion')).toBeNull();
  });
});
