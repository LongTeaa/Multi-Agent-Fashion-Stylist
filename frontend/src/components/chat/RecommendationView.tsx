'use client';

import React from 'react';
import type { StylistChatResponseData } from '@/types/chat';
import { OutfitCard, normalizeStylistItems } from '@/components/outfits/OutfitCard';

export interface RecommendationViewProps {
  data: StylistChatResponseData;
  ratingsMap?: Record<string, number>;
  onRatingChange?: (outfitId: string, rating: number) => void;
}

export const RecommendationView: React.FC<RecommendationViewProps> = ({ data, ratingsMap, onRatingChange }) => {
  const count = data.recommendations.length;

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
    </section>
  );
};
