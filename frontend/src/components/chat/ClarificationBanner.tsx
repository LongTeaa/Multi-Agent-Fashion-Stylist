'use client';

import React from 'react';

interface ClarificationBannerProps {
  question: string;
  onFocusComposer?: () => void;
}

export const ClarificationBanner: React.FC<ClarificationBannerProps> = ({
  question,
  onFocusComposer,
}) => {
  return (
    <div
      role="region"
      aria-label="Yêu cầu làm rõ từ Stylist AI"
      className="w-full bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 rounded-2xl p-5 shadow-sm transition-all"
    >
      <div className="flex items-start gap-3.5">
        <div className="w-10 h-10 rounded-xl bg-amber-500/20 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0 mt-0.5">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-amber-900 dark:text-amber-200">
              Stylist AI Cần Thêm Thông Tin
            </h3>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-200/60 dark:bg-amber-900/60 text-amber-800 dark:text-amber-300">
              Làm rõ bối cảnh
            </span>
          </div>

          <p className="mt-1.5 text-sm sm:text-base text-amber-950 dark:text-amber-100 font-medium leading-relaxed">
            {question}
          </p>

          <div className="mt-3.5 flex items-center gap-3">
            {onFocusComposer && (
              <button
                type="button"
                onClick={onFocusComposer}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold shadow-xs transition"
              >
                <span>Trả lời câu hỏi</span>
                <span>↓</span>
              </button>
            )}
            <span className="text-xs text-amber-700/80 dark:text-amber-400">
              Vui lòng nhập thêm thông tin chi tiết vào khung chat bên trên để AI gợi ý chuẩn xác nhất.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
