'use client';

import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { AppShell, PageHeader } from '@/components/layout/AppShell';
import { useStylistChat } from '@/hooks/useStylistChat';
import { ChatComposer, type ChatComposerRef } from '@/components/chat/ChatComposer';
import { ClarificationBanner } from '@/components/chat/ClarificationBanner';
import { ChatErrorBanner } from '@/components/chat/ChatErrorBanner';
import { RecommendationView } from '@/components/chat/RecommendationView';
import { RatingPrompt } from '@/components/feedback/RatingPrompt';
import { isSessionFeedbackSuppressed } from '@/lib/api';
import { OCCASION_SHORTCUTS, STYLIST_QUERY_PARAM } from '@/lib/occasions';

const emptySubscribe = () => () => {};
const getSessionSuppressedSnapshot = () => isSessionFeedbackSuppressed();
const getServerSnapshot = () => false;

export default function ChatPage() {
  const { status, response, error, isLoading, sendMessage, retry } = useStylistChat();

  const [ratingsMap, setRatingsMap] = useState<Record<string, number>>({});
  const [dismissedPromptRequestId, setDismissedPromptRequestId] = useState<string | null>(null);
  const isSessionSuppressed = useSyncExternalStore(
    emptySubscribe,
    getSessionSuppressedSnapshot,
    getServerSnapshot
  );

  const composerRef = useRef<ChatComposerRef>(null);
  const handledHandoffRef = useRef(false);

  // A request typed on the home page arrives as ?q=...; send it once, then clean the URL.
  useEffect(() => {
    if (handledHandoffRef.current || typeof window === 'undefined') return;
    handledHandoffRef.current = true;
    const params = new URLSearchParams(window.location.search);
    const handoff = params.get(STYLIST_QUERY_PARAM)?.trim().slice(0, 1000);
    if (!handoff) return;
    composerRef.current?.setQueryText(handoff);
    sendMessage(handoff);
    params.delete(STYLIST_QUERY_PARAM);
    const rest = params.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${rest ? `?${rest}` : ''}`);
  }, [sendMessage]);

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

  return (
    <AppShell width="narrow">
      <PageHeader
        title="Hôm nay bạn đi đâu?"
        description="Mô tả dịp, nơi bạn đến hoặc thời tiết. Mỗi bộ phối đều được chọn từ những món đồ trong tủ của bạn."
      />

      <div className="space-y-6">
        <ChatComposer ref={composerRef} onSend={sendMessage} isLoading={isLoading} />

        {status === 'idle' && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-sm text-muted">Thử nhanh:</span>
            {OCCASION_SHORTCUTS.map((occasion) => (
              <button
                key={occasion.label}
                type="button"
                className="chip"
                onClick={() => composerRef.current?.setQueryText(occasion.prompt)}
              >
                {occasion.label}
              </button>
            ))}
          </div>
        )}

        {isLoading && (
          <div role="status" aria-live="polite" className="card space-y-5 p-5 sm:p-6">
            <div className="grid grid-cols-3 gap-3">
              {[0, 1, 2].map((key) => (
                <div key={key} className="aspect-square animate-pulse rounded-xl bg-sunken" />
              ))}
            </div>
            <div className="space-y-2">
              <div className="h-3 w-3/4 animate-pulse rounded bg-sunken" />
              <div className="h-3 w-1/2 animate-pulse rounded bg-sunken" />
            </div>
            <p className="text-sm text-muted">Đang chọn đồ trong tủ của bạn…</p>
          </div>
        )}

        {status === 'clarification' && response?.clarification_question && (
          <ClarificationBanner
            question={response.clarification_question}
            onFocusComposer={() => composerRef.current?.focus()}
          />
        )}

        {status === 'error' && error && <ChatErrorBanner error={error} onRetry={retry} />}

        {status === 'success' && response && (
          <RecommendationView data={response} ratingsMap={ratingsMap} onRatingChange={handleRatingChange} />
        )}
      </div>

      {/* Cadence-driven rating prompt (non-blocking docked card) */}
      {shouldShowRatingPrompt && targetOutfit && (
        <RatingPrompt
          targetOutfitId={targetOutfit.outfit_id}
          targetRank={targetOutfit.rank}
          onRated={(outfitId, stars) => handleRatingChange(outfitId, stars)}
          onDismiss={() => setDismissedPromptRequestId(response?.request_id ?? null)}
        />
      )}
    </AppShell>
  );
}
