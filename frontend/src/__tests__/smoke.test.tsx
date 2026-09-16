import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

function SmokeComponent({ title }: { title: string }) {
  return (
    <div data-testid="smoke-container">
      <h1>{title}</h1>
      <p>Trợ lý thời trang AI</p>
    </div>
  );
}

describe('Frontend Test Foundation Smoke Test', () => {
  it('renders a React component in jsdom and performs DOM assertions', () => {
    render(<SmokeComponent title="Multi-Agent Fashion Stylist" />);
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading).toBeDefined();
    expect(heading.textContent).toBe('Multi-Agent Fashion Stylist');

    const desc = screen.getByText('Trợ lý thời trang AI');
    expect(desc).toBeDefined();

    const container = screen.getByTestId('smoke-container');
    expect(container).toBeDefined();
  });
});
