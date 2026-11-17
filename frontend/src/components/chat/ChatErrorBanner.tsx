'use client';

import React from 'react';
import Link from 'next/link';
import type { ApiError } from '@/lib/api';
import { AlertIcon, CameraIcon, RefreshIcon } from '@/components/ui/icons';

interface ChatErrorBannerProps {
  error: ApiError;
  onRetry?: () => void;
}

function describe(error: ApiError): { title: string; body: string } {
  switch (error.code) {
    case 'WARDROBE_EMPTY':
      return {
        title: 'Tủ đồ đang trống',
        body: 'Thêm vài món bạn hay mặc trước, rồi quay lại đây để nhận bộ phối.',
      };
    case 'NO_COMPLETE_OUTFIT':
      return {
        title: 'Chưa đủ đồ để phối trọn bộ',
        body: 'Tủ đồ hiện chưa có đủ áo, quần hoặc váy và giày hợp với dịp này. Thử thêm đồ hoặc mô tả dịp khác nhé.',
      };
    case 'NETWORK_ERROR':
      return {
        title: 'Mất kết nối',
        body: 'Không kết nối được tới máy chủ. Kiểm tra mạng rồi thử lại.',
      };
    default:
      return {
        title: 'Chưa phối được lúc này',
        body: error.message || 'Đã có lỗi khi xử lý yêu cầu. Vui lòng thử lại.',
      };
  }
}

export const ChatErrorBanner: React.FC<ChatErrorBannerProps> = ({ error, onRetry }) => {
  const isWardrobeEmpty = error.code === 'WARDROBE_EMPTY';
  const isNoCompleteOutfit = error.code === 'NO_COMPLETE_OUTFIT';
  const { title, body } = describe(error);

  return (
    <div role="alert" className="card animate-rise p-5">
      <div className="flex items-start gap-3">
        <AlertIcon size={20} className="mt-0.5 shrink-0 text-danger" />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-ink">{title}</h3>
          <p className="mt-1 text-[0.9375rem] leading-relaxed text-ink-2">{body}</p>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {(isWardrobeEmpty || isNoCompleteOutfit) && (
              <Link href="/wardrobe?add=1" className="btn btn-primary btn-sm">
                <CameraIcon size={15} />
                Thêm món đồ
              </Link>
            )}
            {onRetry && !isWardrobeEmpty && (
              <button type="button" onClick={onRetry} className="btn btn-secondary btn-sm">
                <RefreshIcon size={15} />
                Thử lại
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
