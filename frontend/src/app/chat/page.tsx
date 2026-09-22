'use client';

import React, { useRef, useState, useSyncExternalStore } from 'react';
import { AppHeader } from '@/components/navigation/AppHeader';
import { useStylistChat } from '@/hooks/useStylistChat';
import { ChatComposer, type ChatComposerRef } from '@/components/chat/ChatComposer';
import { ClarificationBanner } from '@/components/chat/ClarificationBanner';
import { ChatErrorBanner } from '@/components/chat/ChatErrorBanner';
import { RecommendationView } from '@/components/chat/RecommendationView';
import { RatingPrompt } from '@/components/feedback/RatingPrompt';
import { isSessionFeedbackSuppressed } from '@/lib/api';

const SUGGESTED_PROMPTS = [
  'Đi cafe ngoài trời ở Đà Lạt, se lạnh, muốn set đồ lịch sự nhẹ nhàng',
  'Đi làm văn phòng ngày hè ở Hà Nội, ưu tiên thoải mái thoáng mát',
  'Dự tiệc sinh nhật bạn thân buổi tối ở TP. Hồ Chí Minh, phong cách smart casual',
  'Dạo phố cuối tuần, thời tiết mát mẻ, phong cách tối giản',
];

const emptySubscribe = () => () => {};
const getSessionSuppressedSnapshot = () => isSessionFeedbackSuppressed();
const getServerSnapshot = () => false;

export default function ChatPage() {
  const {
    status,
    response,
    error,
    isLoading,
    sendMessage,
    retry,
  } = useStylistChat();

  const [ratingsMap, setRatingsMap] = useState<Record<string, number>>({});
  const [dismissedPromptRequestId, setDismissedPromptRequestId] = useState<string | null>(null);
  const isSessionSuppressed = useSyncExternalStore(
    emptySubscribe,
    getSessionSuppressedSnapshot,
    getServerSnapshot
  );

  const handleRatingChange = (outfitId: string, rating: number) => {
    setRatingsMap((prev) => ({ ...prev, [outfitId]: rating }));
  };

  const targetOutfit =
    response?.feedback_prompt_eligible && response.feedback_target_outfit_id
      ? response.recommendations.find((r) => r.outfit_id === response.feedback_target_outfit_id)
      : undefined;

  const isCurrentPromptDismissed =
    Boolean(response?.request_id) && dismissedPromptRequestId === response?.request_id;
  const isSuppressed = isCurrentPromptDismissed || isSessionSuppressed;

  const shouldShowRatingPrompt =
    status === 'success' &&
    Boolean(response?.feedback_prompt_eligible) &&
    Boolean(targetOutfit) &&
    !isSuppressed &&
    ratingsMap[targetOutfit!.outfit_id] === undefined;

  const composerRef = useRef<ChatComposerRef>(null);

  const handleSelectSuggestedPrompt = (prompt: string) => {
    composerRef.current?.setQueryText(prompt);
  };

  const handleFocusComposer = () => {
    composerRef.current?.focus();
  };

  return (
    <div className="min-h-screen bg-[#FBFBF9] text-[#1A1918]">
      <AppHeader />

      {/* Main Content */}
      <main className="max-w-3xl mx-auto px-4 py-8 sm:py-10 space-y-8">
        {/* Page Hero Title */}
        <div className="text-center sm:text-left space-y-2">
          <span className="text-xs font-mono uppercase tracking-widest text-[#9C5234] block">
            Personal Stylist Session
          </span>
          <h1 className="font-serif text-3xl sm:text-4xl font-normal tracking-tight text-[#1A1918]">
            Trợ Lý Phối Đồ Stylist AI
          </h1>
          <p className="text-sm text-[#5C564E] leading-relaxed max-w-xl">
            Mô tả bối cảnh, sự kiện hoặc thời tiết hôm nay. Hệ thống đa tác nhân sẽ chọn lọc trang phục từ chính tủ đồ của bạn để tạo nên các set đồ chuẩn gu.
          </p>
        </div>

        {/* Chat Composer Form */}
        <ChatComposer
          ref={composerRef}
          onSend={sendMessage}
          isLoading={isLoading}
        />

        {/* Quick Suggestion Pills (Shown when idle or after completion) */}
        {status === 'idle' && (
          <div className="space-y-3 pt-2">
            <span className="text-xs font-mono uppercase tracking-wider text-[#736E65] block">
              Gợi ý bối cảnh thường gặp:
            </span>
            <div className="flex flex-wrap gap-2">
              {SUGGESTED_PROMPTS.map((prompt, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleSelectSuggestedPrompt(prompt)}
                  className="tactile-btn px-3.5 py-2 rounded-xl text-xs font-medium text-left bg-white hover:bg-[#F5F4F0] text-[#1A1918] border border-[#E8E5DE] shadow-2xs transition flex items-center gap-2"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-[#9C5234]" aria-hidden="true"></span>
                  <span>{prompt}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Loading State Skeleton */}
        {isLoading && (
          <div
            role="status"
            aria-live="polite"
            className="w-full bg-white rounded-3xl border border-[#E8E5DE] p-6 sm:p-8 space-y-5 shadow-xs animate-pulse"
          >
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-[#EAE8E1]"></div>
              <div className="space-y-2 flex-1">
                <div className="h-4 bg-[#EAE8E1] rounded w-1/3"></div>
                <div className="h-3 bg-[#F5F4F0] rounded w-1/2"></div>
              </div>
            </div>

            <div className="h-20 bg-[#F5F4F0] rounded-2xl"></div>

            <div className="grid grid-cols-3 gap-3 pt-2">
              <div className="h-36 bg-[#F5F4F0] rounded-2xl"></div>
              <div className="h-36 bg-[#F5F4F0] rounded-2xl"></div>
              <div className="h-36 bg-[#F5F4F0] rounded-2xl"></div>
            </div>

            <p className="text-xs text-center text-[#736E65] font-mono tracking-wider pt-2">
              Stylist đang phân tích chất liệu, phom dáng và tính toán bảng màu...
            </p>
          </div>
        )}

        {/* Clarification State */}
        {status === 'clarification' && response?.clarification_question && (
          <ClarificationBanner
            question={response.clarification_question}
            onFocusComposer={handleFocusComposer}
          />
        )}

        {/* Error State */}
        {status === 'error' && error && (
          <ChatErrorBanner error={error} onRetry={retry} />
        )}

        {/* Success Recommendations State */}
        {status === 'success' && response && (
          <RecommendationView
            data={response}
            ratingsMap={ratingsMap}
            onRatingChange={handleRatingChange}
          />
        )}
      </main>

      {/* Cadence Proactive Rating Prompt (Non-blocking docked card) */}
      {shouldShowRatingPrompt && targetOutfit && (
        <RatingPrompt
          targetOutfitId={targetOutfit.outfit_id}
          targetRank={targetOutfit.rank}
          onRated={(outfitId, stars) => {
            handleRatingChange(outfitId, stars);
          }}
          onDismiss={() => {
            setDismissedPromptRequestId(response?.request_id ?? null);
          }}
        />
      )}
    </div>
  );
}
