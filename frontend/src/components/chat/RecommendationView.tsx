'use client';

import React from 'react';
import type { StylistChatResponseData } from '@/types/chat';
import { OutfitCard, normalizeStylistItems } from '@/components/outfits/OutfitCard';

export interface RecommendationViewProps {
  data: StylistChatResponseData;
  ratingsMap?: Record<string, number>;
  onRatingChange?: (outfitId: string, rating: number) => void;
}

export const RecommendationView: React.FC<RecommendationViewProps> = ({
  data,
  ratingsMap,
  onRatingChange,
}) => {
  return (
    <div className="w-full space-y-6 animate-fadeIn">
      {/* Recommendations section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-serif text-xl sm:text-2xl font-normal text-[#1A1918] tracking-tight">
            {data.recommendations.length > 0
              ? `AI Đã Phối ${data.recommendations.length} Set Đồ Dành Riêng Cho Bạn`
              : 'Không có gợi ý nào'}
          </h2>

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
      </div>
    </div>
  );
};
