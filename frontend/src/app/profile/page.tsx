import React from 'react';
import { AppShell, PageHeader } from '@/components/layout/AppShell';
import { ProfilePreferencesForm } from '@/components/profile/ProfilePreferencesForm';

export const metadata = {
  title: 'Gu của tôi',
  description: 'Chọn phong cách, bảng màu và ưu tiên phối đồ của bạn.',
};

export default function ProfilePage() {
  return (
    <AppShell width="narrow">
      <PageHeader
        title="Gu của tôi"
        description="Chọn những gì bạn thích để gợi ý được ưu tiên đúng hướng. Không bắt buộc, có thể đổi bất cứ lúc nào."
      />
      <ProfilePreferencesForm />
    </AppShell>
  );
}
