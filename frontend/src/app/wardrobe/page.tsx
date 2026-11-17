import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { WardrobeView } from '@/components/wardrobe/WardrobeView';

export const metadata = {
  title: 'Tủ đồ',
  description: 'Xem, tìm và thêm quần áo vào tủ đồ của bạn.',
};

export default function WardrobePage() {
  return (
    <AppShell width="wide">
      <WardrobeView />
    </AppShell>
  );
}
