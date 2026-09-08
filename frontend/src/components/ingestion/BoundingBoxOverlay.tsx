'use client';

import React from 'react';
import type { DetectionReviewItem } from '@/types/ingestion';

interface BoundingBoxOverlayProps {
  imageUrl?: string;
  detections: DetectionReviewItem[];
  selectedDetectionId: string | null;
  onSelectDetection: (detectionId: string) => void;
}

export function BoundingBoxOverlay({
  imageUrl,
  detections,
  selectedDetectionId,
  onSelectDetection,
}: BoundingBoxOverlayProps) {
  if (!imageUrl && detections.length === 0) {
    return null;
  }

  return (
    <div className="relative w-full bg-slate-900 rounded-2xl overflow-hidden shadow-2xl border border-slate-700/50 flex flex-col items-center justify-center p-3">
      <div className="relative inline-block max-w-full overflow-hidden rounded-xl">
        {/* Main Original Image */}
        {imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imageUrl}
            alt="Original Ingestion Upload"
            className="max-h-[500px] w-auto object-contain block mx-auto select-none rounded-lg"
          />
        ) : (
          <div className="w-[420px] h-[420px] bg-slate-800 flex flex-col items-center justify-center text-slate-400">
            <svg className="w-12 h-12 mb-2 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span className="text-sm">Ảnh phân tích tổng quan</span>
          </div>
        )}

        {/* Bounding Box Overlays */}
        {detections.map((det, idx) => {
          const [xMin, yMin, xMax, yMax] = det.bounding_box;
          const left = `${xMin * 100}%`;
          const top = `${yMin * 100}%`;
          const width = `${Math.max(0.02, xMax - xMin) * 100}%`;
          const height = `${Math.max(0.02, yMax - yMin) * 100}%`;

          const isSelected = selectedDetectionId === det.detection_id;
          const categoryConf = det.field_confidence.category || 0.95;
          const categoryLabel = det.attributes.category || `Món đồ #${idx + 1}`;

          return (
            <div
              key={det.detection_id}
              onClick={() => onSelectDetection(det.detection_id)}
              style={{ top, left, width, height }}
              className={`absolute cursor-pointer transition-all duration-200 rounded-md group ${
                isSelected
                  ? 'border-2 border-indigo-400 bg-indigo-500/25 shadow-[0_0_15px_rgba(99,102,241,0.6)] z-20'
                  : 'border-2 border-emerald-400/80 bg-emerald-500/10 hover:bg-emerald-500/20 hover:border-emerald-300 z-10'
              }`}
            >
              {/* Badge Tag */}
              <div
                className={`absolute -top-7 left-0 px-2 py-0.5 rounded text-[11px] font-semibold whitespace-nowrap shadow-md flex items-center gap-1.5 transition-transform ${
                  isSelected
                    ? 'bg-indigo-600 text-white scale-105'
                    : 'bg-slate-900/90 text-emerald-300 group-hover:bg-slate-900'
                }`}
              >
                <span className="capitalize">{categoryLabel}</span>
                <span className="text-[9px] opacity-80">({Math.round(categoryConf * 100)}%)</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-3 text-xs text-slate-400 flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-emerald-400"></span>
        <span>Click vào các khung trên ảnh để xem và hiệu đính chi tiết từng món đồ.</span>
      </div>
    </div>
  );
}
