'use client';

import React from 'react';
import type { StylistChatResponseData, StylistContext } from '@/types/chat';
import { OutfitCard, normalizeStylistItems } from '@/components/outfits/OutfitCard';

export interface RecommendationViewProps {
  data: StylistChatResponseData;
  ratingsMap?: Record<string, number>;
  onRatingChange?: (outfitId: string, rating: number) => void;
}

const ContextSummary: React.FC<{ context: StylistContext }> = ({ context }) => {
  return (
    <div className="bg-[#FAF8F5] border border-[#E8E5DE] rounded-3xl p-5 sm:p-6 mb-8 shadow-2xs">
      <div className="flex items-center gap-2.5 mb-4">
        <span className="w-2 h-2 rounded-full bg-[#9C5234]"></span>
        <h4 className="text-xs font-mono font-semibold uppercase tracking-widest text-[#736E65]">
          Ngữ Cảnh Được AI Nhận Diện
        </h4>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        {context.occasion && (
          <div className="p-3.5 rounded-2xl bg-white border border-[#E8E5DE] shadow-2xs">
            <span className="text-[#736E65] block text-[10px] font-mono uppercase tracking-wider">Dịp / Sự kiện</span>
            <span className="font-serif text-sm font-medium text-[#1A1918] capitalize mt-0.5 block">
              {context.occasion}
            </span>
          </div>
        )}

        {context.location_text && (
          <div className="p-3.5 rounded-2xl bg-white border border-[#E8E5DE] shadow-2xs">
            <span className="text-[#736E65] block text-[10px] font-mono uppercase tracking-wider">Địa điểm</span>
            <span className="font-serif text-sm font-medium text-[#1A1918] mt-0.5 block">
              {context.location_text}
            </span>
          </div>
        )}

        {(context.weather_condition || context.temperature_celsius !== null) && (
          <div className="p-3.5 rounded-2xl bg-white border border-[#E8E5DE] shadow-2xs">
            <span className="text-[#736E65] block text-[10px] font-mono uppercase tracking-wider">Thời tiết</span>
            <span className="font-serif text-sm font-medium text-[#1A1918] mt-0.5 block">
              {context.temperature_celsius !== null && context.temperature_celsius !== undefined
                ? `${context.temperature_celsius}°C`
                : ''}{' '}
              {context.weather_condition ? `(${context.weather_condition})` : ''}
            </span>
          </div>
        )}

        {context.target_formality_range?.length > 0 && (
          <div className="p-3.5 rounded-2xl bg-white border border-[#E8E5DE] shadow-2xs">
            <span className="text-[#736E65] block text-[10px] font-mono uppercase tracking-wider">Độ trang trọng mục tiêu</span>
            <span className="font-serif text-sm font-medium text-[#1A1918] mt-0.5 block">
              Mức {context.target_formality_range.join(' – ')}/5
            </span>
          </div>
        )}
      </div>

      {context.style_hints?.length > 0 && (
        <div className="mt-4 pt-3 border-t border-[#E8E5DE] flex items-center gap-2 flex-wrap">
          <span className="text-xs font-mono text-[#736E65]">Phong cách gợi ý:</span>
          {context.style_hints.map((hint, idx) => (
            <span
              key={idx}
              className="px-3 py-1 rounded-full text-xs font-mono bg-white text-[#1A1918] border border-[#E8E5DE] shadow-2xs"
            >
              #{hint}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

export const RecommendationView: React.FC<RecommendationViewProps> = ({
  data,
  ratingsMap,
  onRatingChange,
}) => {
  return (
    <div className="w-full space-y-6 animate-fadeIn">
      {/* Extracted context snapshot */}
      {data.context && <ContextSummary context={data.context} />}

      {/* Recommendations section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-serif text-xl sm:text-2xl font-normal text-[#1A1918] tracking-tight">
            {data.recommendations.length > 0
              ? `AI Đã Phối ${data.recommendations.length} Set Đồ Dành Riêng Cho Bạn`
              : 'Không có gợi ý nào'}
          </h2>
          <span className="text-xs text-[#736E65] font-mono">
            Mã yêu cầu: {data.request_id?.slice(0, 8) ?? ''}
          </span>
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
