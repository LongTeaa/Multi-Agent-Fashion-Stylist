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
    <div className="relative w-full bg-[#1A1918] rounded-3xl overflow-hidden shadow-xl border border-[#E8E5DE] flex flex-col items-center justify-center p-3">
      <div className="relative inline-block max-w-full overflow-hidden rounded-2xl">
        {/* Main Original Image */}
        {imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imageUrl}
            alt="Original Ingestion Upload"
            className="max-h-[500px] w-auto object-contain block mx-auto select-none rounded-xl"
          />
        ) : (
          <div className="w-[420px] h-[420px] bg-[#242220] flex flex-col items-center justify-center text-[#736E65]">
            <svg className="w-12 h-12 mb-2 text-[#736E65]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span className="text-xs font-mono">Ảnh phân tích tổng quan</span>
          </div>
        )}

        {/* Bounding Box Overlays */}
        {imageUrl && detections.map((det, idx) => {
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
              className={`absolute cursor-pointer transition-all duration-200 rounded-lg group ${
                isSelected
                  ? 'border-2 border-[#9C5234] bg-[#9C5234]/25 shadow-[0_0_15px_rgba(156,82,52,0.5)] z-20'
                  : 'border-2 border-white/70 bg-white/10 hover:bg-white/25 hover:border-white z-10'
              }`}
            >
              {/* Badge Tag */}
              <div
                className={`absolute -top-7 left-0 px-2.5 py-0.5 rounded-full text-[10px] font-mono tracking-wider whitespace-nowrap shadow-md flex items-center gap-1.5 transition-transform ${
                  isSelected
                    ? 'bg-[#9C5234] text-white scale-105'
                    : 'bg-[#1A1918]/85 text-white/90 backdrop-blur-md group-hover:bg-[#1A1918]'
                }`}
              >
                <span className="capitalize">{categoryLabel}</span>
                <span className="text-[9px] opacity-80">({Math.round(categoryConf * 100)}%)</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-3 text-xs font-mono text-[#A8A29E] flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-[#9C5234]"></span>
        <span>
          {imageUrl
            ? 'Click vào các khung trên ảnh để xem và hiệu đính chi tiết từng món đồ.'
            : 'Batch có nhiều ảnh. Vui lòng xem từng ảnh crop trong danh sách phát hiện.'}
        </span>
      </div>
    </div>
  );
}
