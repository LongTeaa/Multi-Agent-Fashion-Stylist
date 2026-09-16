'use client';

import React from 'react';
import Link from 'next/link';
import type { ApiError } from '@/lib/api';

interface ChatErrorBannerProps {
  error: ApiError;
  onRetry?: () => void;
}

export const ChatErrorBanner: React.FC<ChatErrorBannerProps> = ({ error, onRetry }) => {
  const isWardrobeEmpty = error.code === 'WARDROBE_EMPTY';
  const isNoCompleteOutfit = error.code === 'NO_COMPLETE_OUTFIT';
  const isNetworkError = error.code === 'NETWORK_ERROR';

  return (
    <div
      role="alert"
      className="w-full bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800/60 rounded-2xl p-5 shadow-sm transition-all"
    >
      <div className="flex items-start gap-3.5">
        <div className="w-10 h-10 rounded-xl bg-rose-500/20 text-rose-600 dark:text-rose-400 flex items-center justify-center shrink-0 mt-0.5">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-rose-900 dark:text-rose-200">
              {isWardrobeEmpty
                ? 'Tủ Đồ Chưa Có Trang Phục'
                : isNoCompleteOutfit
                ? 'Không Thể Tạo Bộ Phối Hoàn Chỉnh'
                : isNetworkError
                ? 'Lỗi Kết Nối Mạng'
                : 'Đã Xảy Ra Lỗi'}
            </h3>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-rose-200/60 dark:bg-rose-900/60 text-rose-800 dark:text-rose-300">
              {error.code}
            </span>
          </div>

          <p className="mt-1.5 text-sm text-rose-950 dark:text-rose-100 leading-relaxed">
            {isWardrobeEmpty
              ? 'Tủ đồ của bạn hiện chưa có trang phục nào khả dụng để phối. Vui lòng tải ảnh và số hóa các món đồ của bạn trước khi nhờ AI tư vấn.'
              : isNoCompleteOutfit
              ? 'AI không thể tạo đủ bộ ba món (áo, quần/váy, giày) phù hợp với bối cảnh và yêu cầu độ trang trọng này từ tủ đồ hiện tại của bạn. Bạn hãy bổ sung thêm trang phục hoặc điều chỉnh bối cảnh nhé.'
              : error.message || 'Không thể thực hiện yêu cầu tư vấn phối đồ vào lúc này.'}
          </p>

          <div className="mt-4 flex items-center gap-3">
            {isWardrobeEmpty && (
              <Link
                href="/wardrobe"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition"
              >
                <span>Số Hóa Tủ Đồ Ngay</span>
                <span>→</span>
              </Link>
            )}

            {onRetry && !isWardrobeEmpty && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-xs transition"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                <span>Thử lại</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
