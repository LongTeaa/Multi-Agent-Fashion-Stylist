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
    <div className="bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 rounded-2xl p-4 sm:p-5 mb-6">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Ngữ Cảnh Được AI Nhận Diện
        </h4>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        {context.occasion && (
          <div className="p-2.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50">
            <span className="text-slate-400 block text-[10px]">Dịp / Sự kiện</span>
            <span className="font-semibold text-slate-700 dark:text-slate-200 capitalize">
              {context.occasion}
            </span>
          </div>
        )}

        {context.location_text && (
          <div className="p-2.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50">
            <span className="text-slate-400 block text-[10px]">Địa điểm</span>
            <span className="font-semibold text-slate-700 dark:text-slate-200">
              {context.location_text}
            </span>
          </div>
        )}

        {(context.weather_condition || context.temperature_celsius !== null) && (
          <div className="p-2.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50">
            <span className="text-slate-400 block text-[10px]">Thời tiết</span>
            <span className="font-semibold text-slate-700 dark:text-slate-200">
              {context.temperature_celsius !== null && context.temperature_celsius !== undefined
                ? `${context.temperature_celsius}°C`
                : ''}{' '}
              {context.weather_condition ? `(${context.weather_condition})` : ''}
            </span>
          </div>
        )}

        {context.target_formality_range?.length > 0 && (
          <div className="p-2.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50">
            <span className="text-slate-400 block text-[10px]">Độ trang trọng mục tiêu</span>
            <span className="font-semibold text-slate-700 dark:text-slate-200">
              Mức {context.target_formality_range.join(' – ')}/5
            </span>
          </div>
        )}
      </div>

      {context.style_hints?.length > 0 && (
        <div className="mt-3 flex items-center gap-1.5 flex-wrap">
          <span className="text-[11px] text-slate-400">Phong cách gợi ý:</span>
          {context.style_hints.map((hint, idx) => (
            <span
              key={idx}
              className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200/50 dark:border-indigo-800/40"
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
          <h2 className="text-base sm:text-lg font-bold text-slate-800 dark:text-slate-100">
            {data.recommendations.length > 0
              ? `AI Đã Phối ${data.recommendations.length} Set Đồ Dành Riêng Cho Bạn`
              : 'Không có gợi ý nào'}
          </h2>
          <span className="text-xs text-slate-400 font-mono">
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
