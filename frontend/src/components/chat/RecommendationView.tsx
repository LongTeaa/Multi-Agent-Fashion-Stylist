'use client';

import React from 'react';
import type { StylistChatResponseData } from '@/types/chat';
import { OutfitCard, normalizeStylistItems } from '@/components/outfits/OutfitCard';

const AGENT_LABELS: Record<string, string> = {
  context: 'Hiểu yêu cầu',
  wardrobe: 'Tìm trong tủ đồ',
  fashion: 'Phối và chấm điểm',
  personalization: 'Theo gu của bạn',
  coordinator: 'Kiểm tra và tổng hợp',
  end: 'Hoàn tất',
};

export interface RecommendationViewProps {
  data: StylistChatResponseData;
  ratingsMap?: Record<string, number>;
  onRatingChange?: (outfitId: string, rating: number) => void;
}

export const RecommendationView: React.FC<RecommendationViewProps> = ({ data, ratingsMap, onRatingChange }) => {
  const count = data.recommendations.length;
  const trace = data.agent_trace ?? [];
  const hasFeedbackLoop = trace.some(
    (ev) => ev.event_type === 'RELAXATION_REQUESTED' || ev.event_type.startsWith('CRITIQUE_')
  );

  return (
    <section aria-labelledby="recommendations-heading" className="animate-rise space-y-5 pt-2">
      <div className="flex items-baseline justify-between gap-3 border-b border-line pb-3">
        <h2 id="recommendations-heading" className="display text-2xl">
          {count > 0 ? `${count} bộ phối cho bạn` : 'Chưa có bộ phối phù hợp'}
        </h2>
        {count > 1 && <span className="text-sm text-muted">Xếp theo độ phù hợp</span>}
      </div>

      <div className="space-y-5">
        {data.recommendations.map((rec) => (
          <OutfitCard
            key={rec.outfit_id}
            outfitId={rec.outfit_id}
            testId="outfit-recommendation-card"
            rank={rec.rank}
            compositeScore={rec.composite_score}
            explanationVi={rec.explanation_vi}
            appliedPreferences={rec.applied_preferences}
            items={normalizeStylistItems(rec.items)}
            initialIsBookmarked={false}
            initialTimesWorn={0}
            initialRating={ratingsMap?.[rec.outfit_id] ?? null}
            onRatingChange={onRatingChange}
          />
        ))}
      </div>

      {trace.length > 0 && (
        <details
          data-testid="agent-trace-panel"
          className="card px-4 py-3 text-sm sm:px-5"
        >
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 font-medium text-ink">
            <span>
              Cách hệ thống chọn bộ phối ({trace.length} bước
              {hasFeedbackLoop ? ' · có bước tìm lại' : ''})
            </span>
            <span className="text-xs text-muted">Chi tiết</span>
          </summary>

          <ol className="mt-3 space-y-2 border-t border-line pt-3">
            {trace.map((step, idx) => {
              const isLoopStep =
                step.event_type === 'RELAXATION_REQUESTED' ||
                step.event_type === 'RELAXATION_APPLIED' ||
                step.event_type.startsWith('CRITIQUE_');
              return (
                <li
                  key={`${step.sender}-${step.receiver}-${idx}`}
                  className="flex flex-col gap-0.5 rounded-lg bg-paper px-3 py-2 text-xs sm:flex-row sm:items-baseline sm:justify-between sm:gap-3"
                >
                  <div className="flex flex-wrap items-center gap-1.5 font-semibold text-ink">
                    <span className={isLoopStep ? 'text-accent' : 'text-ink-2'}>
                      {AGENT_LABELS[step.sender] ?? step.sender} → {AGENT_LABELS[step.receiver] ?? step.receiver}
                    </span>
                    {step.round > 0 && (
                      <span className="hang-tag">Vòng {step.round}</span>
                    )}
                  </div>
                  <span className="text-muted sm:text-right">{step.summary_vi}</span>
                </li>
              );
            })}
          </ol>
        </details>
      )}
    </section>
  );
};
