import Link from 'next/link';

import { ProfilePreferencesForm } from '@/components/profile/ProfilePreferencesForm';

export const metadata = {
  title: 'Sở thích phong cách - Fashion Stylist AI',
  description: 'Chọn phong cách, bảng màu và ưu tiên phối đồ của bạn.',
};

export default function ProfilePage() {
  return (
    <main className="min-h-screen bg-slate-950 px-4 py-10 text-white">
      <div className="mx-auto max-w-3xl">
        <Link href="/" className="text-sm text-indigo-300 hover:text-indigo-200">Về trang chủ</Link>
        <header className="mb-10 mt-6">
          <h1 className="text-3xl font-bold">Sở thích phong cách</h1>
          <p className="mt-3 max-w-2xl text-slate-400">
            Chọn các lựa chọn phù hợp để hệ thống ưu tiên trang phục trong tủ đồ của bạn.
            Bạn có thể bỏ qua hoặc chỉnh sửa bất cứ lúc nào.
          </p>
        </header>
        <ProfilePreferencesForm />
      </div>
    </main>
  );
}
