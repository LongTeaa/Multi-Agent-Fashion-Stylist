'use client';

import React from 'react';
import type { StylistChatResponseData, StylistRecommendation, StylistContext } from '@/types/chat';
import { getMediaUrl } from '@/lib/api';

interface RecommendationViewProps {
  data: StylistChatResponseData;
}

const SLOT_NAMES: Record<string, string> = {
  top: 'Áo',
  bottom: 'Quần / Váy',
  shoes: 'Giày / Dép',
};

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

const RecommendationCard: React.FC<{ recommendation: StylistRecommendation }> = ({
  recommendation,
}) => {
  const matchPercentage = Math.round(recommendation.composite_score * 100);

  return (
    <article
      data-testid="outfit-recommendation-card"
      data-outfit-id={recommendation.outfit_id}
      className="w-full bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700/80 shadow-sm overflow-hidden transition-all hover:shadow-md"
    >
      {/* Card Header */}
      <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-700/60 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span
            className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-black ${
              recommendation.rank === 1
                ? 'bg-amber-500 text-white shadow-xs shadow-amber-500/30'
                : recommendation.rank === 2
                ? 'bg-slate-400 text-white'
                : 'bg-amber-800 text-amber-100'
            }`}
          >
            #{recommendation.rank}
          </span>
          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">
            Gợi Ý Phối Đồ Số {recommendation.rank}
          </h3>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400">Độ phù hợp:</span>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200/60 dark:border-indigo-800/60">
            {matchPercentage}%
          </span>
        </div>
      </div>

      {/* Card Body */}
      <div className="p-5">
        {/* Stylist Explanation */}
        <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed italic border-l-2 border-indigo-500 pl-3 mb-5">
          &ldquo;{recommendation.explanation_vi}&rdquo;
        </p>

        {/* Garment Items Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
          {recommendation.items.map((item) => {
            const imageUrl = item.image_url ? getMediaUrl(item.image_url) : null;
            const slotName = SLOT_NAMES[item.slot] || item.slot;

            return (
              <div
                key={item.item_id}
                className="flex sm:flex-col items-center sm:items-start gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-800"
              >
                {/* Thumbnail */}
                <div className="w-16 h-16 sm:w-full sm:h-36 rounded-lg bg-slate-200 dark:bg-slate-800 overflow-hidden relative shrink-0 flex items-center justify-center">
                  {imageUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={imageUrl}
                      alt={item.name}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <span className="text-slate-400 text-xs font-medium">Không có ảnh</span>
                  )}
                  <span className="absolute top-1.5 left-1.5 px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-black/60 text-white backdrop-blur-xs">
                    {slotName}
                  </span>
                </div>

                {/* Info */}
                <div className="min-w-0 flex-1">
                  <h4 className="text-xs sm:text-sm font-semibold text-slate-800 dark:text-slate-200 truncate">
                    {item.name}
                  </h4>
                  <span className="text-[11px] text-slate-400 capitalize block">
                    Vị trí: {slotName}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Applied Preferences */}
        {recommendation.applied_preferences?.length > 0 && (
          <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] text-slate-400 font-medium">Đã áp dụng gu thời trang:</span>
            {recommendation.applied_preferences.map((pref, idx) => (
              <span
                key={idx}
                className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
              >
                ✓ {pref}
              </span>
            ))}
          </div>
        )}
      </div>
    </article>
  );
};

export const RecommendationView: React.FC<RecommendationViewProps> = ({ data }) => {
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

        <div className="space-y-4">
          {data.recommendations.map((rec) => (
            <RecommendationCard key={rec.outfit_id} recommendation={rec} />
          ))}
        </div>
      </div>
    </div>
  );
};
