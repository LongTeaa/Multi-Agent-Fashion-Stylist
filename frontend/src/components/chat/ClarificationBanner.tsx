'use client';

import React from 'react';

interface ClarificationBannerProps {
  question: string;
  onFocusComposer?: () => void;
}

/** The stylist needs one more detail before choosing outfits. */
export const ClarificationBanner: React.FC<ClarificationBannerProps> = ({ question, onFocusComposer }) => {
  return (
    <div
      role="region"
      aria-label="Câu hỏi làm rõ từ stylist"
      className="card animate-rise border-l-4 border-l-accent p-5"
    >
      <p className="eyebrow">Cần thêm một chút thông tin</p>
      <p className="mt-2 text-[1.0625rem] leading-relaxed text-ink">{question}</p>
      {onFocusComposer && (
        <button type="button" onClick={onFocusComposer} className="btn btn-secondary btn-sm mt-4">
          Trả lời
        </button>
      )}
    </div>
  );
};
