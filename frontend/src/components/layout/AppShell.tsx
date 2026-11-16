import React from 'react';
import { AppHeader } from '@/components/navigation/AppHeader';

const WIDTHS = {
  narrow: 'max-w-3xl',
  default: 'max-w-4xl',
  wide: 'max-w-6xl',
} as const;

interface AppShellProps {
  children: React.ReactNode;
  width?: keyof typeof WIDTHS;
}

/** Page frame shared by every in-app screen. Leaves room for the mobile tab bar. */
export function AppShell({ children, width = 'default' }: AppShellProps) {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <AppHeader />
      <main className={`mx-auto w-full ${WIDTHS[width]} px-4 pb-28 pt-6 sm:px-6 sm:pt-10 md:pb-16`}>
        {children}
      </main>
    </div>
  );
}

interface PageHeaderProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0 space-y-2">
        <h1 className="display text-[2rem] sm:text-[2.5rem]">{title}</h1>
        {description && <p className="max-w-xl text-[0.9375rem] leading-relaxed text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
