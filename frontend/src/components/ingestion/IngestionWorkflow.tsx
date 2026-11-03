'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import type {
  FashionAttributes,
  IngestionBatchReviewResponse,
} from '@/types/ingestion';
import {
  ApiError,
  uploadIngestionImages,
  getIngestionBatch,
  confirmIngestionBatch,
  deleteIngestionBatch,
  updateDetectionCrop,
} from '@/lib/api';
import { useGarmentTaxonomy } from '@/lib/useGarmentTaxonomy';
import { UploadDropzone } from './UploadDropzone';
import { CropEditor } from './CropEditor';
import { PrivateMediaImage } from '@/components/media/PrivateMediaImage';
import { DetectionItemCard } from './DetectionItemCard';

type WorkflowStep = 'upload' | 'processing' | 'review' | 'confirmed' | 'failed';

interface IngestionWorkflowProps {
  onFinish?: (createdItemIds: string[]) => void;
}

export function IngestionWorkflow({ onFinish }: IngestionWorkflowProps) {
  const { taxonomy, taxonomyError, retryTaxonomy } = useGarmentTaxonomy();
  const [step, setStep] = useState<WorkflowStep>(() => {
    if (typeof window !== 'undefined' && sessionStorage.getItem('active_ingestion_batch_id')) {
      return 'processing';
    }
    return 'upload';
  });
  const [isUploading, setIsUploading] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isCropSaving, setIsCropSaving] = useState(false);
  const [batchId, setBatchId] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      return sessionStorage.getItem('active_ingestion_batch_id');
    }
    return null;
  });
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [batchReview, setBatchReview] = useState<IngestionBatchReviewResponse | null>(null);
  const [selectedDetectionId, setSelectedDetectionId] = useState<string | null>(null);
  const [acceptedDetections, setAcceptedDetections] = useState<Record<string, boolean>>({});
  const [editedAttributes, setEditedAttributes] = useState<Record<string, FashionAttributes>>({});
  const [confirmedItemIds, setConfirmedItemIds] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isPollingCancelledRef = useRef<boolean>(false);
  const idempotencyTokenRef = useRef<string>(crypto.randomUUID());

  useEffect(() => {
    if (selectedSourceId) sessionStorage.setItem('active_ingestion_source_id', selectedSourceId);
  }, [selectedSourceId]);

  // Clean up polling timer
  useEffect(() => {
    return () => {
      isPollingCancelledRef.current = true;
      if (pollingTimerRef.current) {
        clearTimeout(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
    };
  }, []);

  // Poll for batch status until ready or failed using recursive awaited polling (no overlapping requests)
  const startPollingBatch = useCallback((id: string) => {
    let consecutiveErrors = 0;
    // A processing batch remains recoverable until the server reports a terminal state.
    isPollingCancelledRef.current = false;

    if (pollingTimerRef.current) {
      clearTimeout(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }

    const poll = async () => {
      if (isPollingCancelledRef.current) return;
      try {
        const review = await getIngestionBatch(id);
        consecutiveErrors = 0;
        if (isPollingCancelledRef.current) return;

        if (review.status === 'needs_review') {
          setBatchReview(review);

          // Initialize accepted states & edited attributes map
          const acceptedMap: Record<string, boolean> = {};
          const attrMap: Record<string, FashionAttributes> = {};
          for (const det of review.detections) {
            acceptedMap[det.detection_id] = true;
            attrMap[det.detection_id] = { ...det.attributes };
          }
          setAcceptedDetections(acceptedMap);
          setEditedAttributes(attrMap);
          if (review.detections.length > 0) {
            const savedSource = sessionStorage.getItem('active_ingestion_source_id');
            const selected = review.detections.find((detection) => detection.source_media_asset_id === savedSource)
              || review.detections[0];
            setSelectedDetectionId(selected.detection_id);
            setSelectedSourceId(selected.source_media_asset_id || null);
          }
          setStep('review');
          return;
        } else if (review.status === 'failed' || review.status === 'expired') {
          setBatchReview(review);
          if (typeof window !== 'undefined') {
            sessionStorage.removeItem('active_ingestion_batch_id');
            sessionStorage.removeItem('active_ingestion_source_id');
          }
          setErrorMessage(
            review.status === 'expired'
              ? 'Lượt tải ảnh đã hết hạn. Vui lòng tải lại ảnh.'
              : 'Chưa thể phân tích ảnh. Vui lòng thử lại với ảnh rõ hơn.'
          );
          setStep('failed');
          return;
        } else if (review.status === 'confirmed') {
          if (typeof window !== 'undefined') {
            sessionStorage.removeItem('active_ingestion_batch_id');
            sessionStorage.removeItem('active_ingestion_source_id');
          }
          setStep('upload');
          return;

        }
      } catch (err: unknown) {
        if (isPollingCancelledRef.current) return;
        consecutiveErrors += 1;
        if (consecutiveErrors >= 5) {
          // Keep the batch ID so reload can resume after a network failure.
          setErrorMessage((err as Error).message || 'Không thể lấy thông tin kết quả phân tích.');
          setStep('failed');
          return;
        }
      }

      if (!isPollingCancelledRef.current) {
        pollingTimerRef.current = setTimeout(poll, 1500);
      }
    };

    // Run first check immediately, then schedule subsequent poll only after response completes
    poll();
  }, []);

  // On initial mount, resume polling if restoring an in-flight batch from session storage
  useEffect(() => {
    if (batchId && step === 'processing') {
      startPollingBatch(batchId);
    }
  }, [batchId, step, startPollingBatch]);

  const handleUpload = async (files: File[], declaredKind?: string) => {
    setIsUploading(true);
    setErrorMessage(null);
    try {
      const res = await uploadIngestionImages(files, declaredKind);
      if (typeof window !== 'undefined') {
        sessionStorage.setItem('active_ingestion_batch_id', res.batch_id);
        sessionStorage.removeItem('active_ingestion_source_id');
      }
      setSelectedSourceId(null);
      setBatchId(res.batch_id);
      setStep('processing');
      // The processing-state effect owns the polling loop.
    } catch (err: unknown) {
      setErrorMessage((err as Error).message || 'Tải ảnh lên thất bại.');
      throw err;
    } finally {
      setIsUploading(false);
    }
  };

  const handleToggleAccepted = (detectionId: string, accepted: boolean) => {
    setAcceptedDetections((prev) => ({
      ...prev,
      [detectionId]: accepted,
    }));
  };

  const handleUpdateAttribute = (detectionId: string, key: string, value: unknown) => {
    setEditedAttributes((prev) => {
      const current = prev[detectionId] || ({} as FashionAttributes);
      return {
        ...prev,
        [detectionId]: {
          ...current,
          [key]: value,
        },
      };
    });
  };

  const handleConfirmBatch = async () => {
    if (!batchId || !batchReview || isConfirming || isCancelling || isCropSaving) return;

    // Validate that all accepted detections have a valid category selected
    const hasUnsetCategory = batchReview.detections.some((det) => {
      const isAccepted = !!acceptedDetections[det.detection_id];
      if (!isAccepted) return false;
      const attrs = editedAttributes[det.detection_id] || det.attributes;
      return !attrs?.category || attrs.category === 'unknown';
    });

    if (hasUnsetCategory) {
      setErrorMessage(
        'Vui lòng chọn danh mục chính hợp lệ cho tất cả các món đồ được chọn lưu trước khi xác nhận.'
      );
      return;
    }

    setIsConfirming(true);
    setErrorMessage(null);

    const confirmations = batchReview.detections.map((det) => ({
      detection_id: det.detection_id,
      accepted: !!acceptedDetections[det.detection_id],
      custom_attributes: editedAttributes[det.detection_id] || det.attributes,
    }));

    try {
      const res = await confirmIngestionBatch(batchId, {
        idempotency_token: idempotencyTokenRef.current,
        confirmations,
      });

      setConfirmedItemIds(res.wardrobe_item_ids);
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('active_ingestion_batch_id');
        sessionStorage.removeItem('active_ingestion_source_id');
      }
      setStep('confirmed');
      if (onFinish) {
        onFinish(res.wardrobe_item_ids);
      }
    } catch (err: unknown) {
      setErrorMessage((err as Error).message || 'Xác nhận món đồ thất bại. Vui lòng thử lại.');
    } finally {
      setIsConfirming(false);
    }
  };

  const handleCancelBatch = async () => {
    if (!batchId || isCancelling || isConfirming || isCropSaving) {
      if (!batchId) handleReset();
      return;
    }

    const confirmed = window.confirm(
      'Bạn có chắc chắn muốn hủy bỏ lượt tải lên này? Toàn bộ ảnh tạm và phân tích AI sẽ bị xóa sạch.'
    );
    if (!confirmed) return;

    setIsCancelling(true);
    setErrorMessage(null);
    try {
      await deleteIngestionBatch(batchId);
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('active_ingestion_batch_id');
        sessionStorage.removeItem('active_ingestion_source_id');
      }
      setIsCancelling(false);
      handleReset();
    } catch (err: unknown) {
      setIsCancelling(false);
      const isAlreadyGone =
        err instanceof ApiError && (err.status === 404 || err.code === 'ITEM_NOT_FOUND');
      if (isAlreadyGone) {
        handleReset();
      } else {
        setErrorMessage(
          (err as Error).message || 'Hủy bỏ lượt tải lên thất bại. Vui lòng thử lại.'
        );
      }
    }
  };

  const handleReset = () => {
    isPollingCancelledRef.current = true;
    if (pollingTimerRef.current) {
      clearTimeout(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
    idempotencyTokenRef.current = crypto.randomUUID();
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem('active_ingestion_batch_id');
      sessionStorage.removeItem('active_ingestion_source_id');
    }
    setStep('upload');
    setSelectedSourceId(null);
    setBatchId(null);
    setBatchReview(null);
    setSelectedDetectionId(null);
    setAcceptedDetections({});
    setEditedAttributes({});
    setConfirmedItemIds([]);
    setErrorMessage(null);
  };

  const sources = batchReview?.source_images ?? [];
  const source = selectedSourceId === 'unassigned' ? undefined : sources.find((entry) => entry.media_asset_id === (selectedSourceId ?? batchReview?.detections.find((det) => det.detection_id === selectedDetectionId)?.source_media_asset_id)) ?? sources[0];
  const visibleDetections = source
    ? (batchReview?.detections ?? []).filter((det) => det.source_media_asset_id === source.media_asset_id)
    : (batchReview?.detections ?? []).filter((det) => sources.length === 0 || !det.source_media_asset_id);

  const needsReviewCount = (batchReview?.detections ?? []).filter((det) => {
    if (!acceptedDetections[det.detection_id]) return false;
    const attrs = editedAttributes[det.detection_id] ?? det.attributes;
    return !attrs.category || attrs.category === 'unknown' || Object.entries(det.field_confidence).some(
      ([field, confidence]) => !(field === 'length' && ['footwear', 'accessory'].includes(attrs.category))
        && confidence < .70 && attrs[field] === det.attributes[field]
    );
  }).length;
  const acceptedCount = Object.values(acceptedDetections).filter(Boolean).length;

  return (
    <div className="w-full max-w-7xl 2xl:max-w-[1480px] mx-auto px-2 sm:px-4 lg:px-6 py-8">
      {/* Step Tracker */}
      <div className="mb-10">
        <div className="flex items-center justify-center max-w-2xl mx-auto px-1">
          {[
            { key: 'upload', label: '1. Tải ảnh lên' },
            { key: 'processing', label: '2. AI phân tích' },
            { key: 'review', label: '3. Kiểm duyệt & Lưu' },
            { key: 'confirmed', label: '4. Hoàn tất' },
          ].map((s, idx) => {
            const isCurrent = step === s.key;
            const isCompleted =
              (s.key === 'upload' && step !== 'upload') ||
              (s.key === 'processing' && (step === 'review' || step === 'confirmed')) ||
              (s.key === 'review' && step === 'confirmed');

            return (
              <React.Fragment key={s.key}>
                {idx > 0 && (
                  <div
                    className={`flex-1 h-[2px] transition-colors ${
                      isCompleted ? 'bg-[#9C5234]' : 'bg-[#E8E5DE]'
                    }`}
                  />
                )}
                <div className="flex shrink-0 flex-col items-center">
                  <div
                    aria-current={isCurrent ? 'step' : undefined}
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-mono transition-all ${
                      isCompleted
                        ? 'bg-[#9C5234] text-white font-medium shadow-2xs'
                        : isCurrent
                        ? 'bg-[#1A1918] text-[#FBFBF9] ring-4 ring-[#1A1918]/10 font-bold scale-105 shadow-xs'
                        : 'bg-[#EAE8E1] text-[#736E65]'
                    }`}
                  >
                    {isCompleted ? '✓' : idx + 1}
                  </div>
                  <span
                    className={`hidden sm:block text-[11px] font-mono mt-2 whitespace-nowrap uppercase tracking-wider ${
                      isCurrent
                        ? 'text-[#1A1918] font-semibold'
                        : isCompleted
                        ? 'text-[#9C5234] font-medium'
                        : 'text-[#736E65]'
                    }`}
                  >
                    {s.label}
                  </span>
                </div>
              </React.Fragment>
            );
          })}
        </div>
        <p className="mt-3 text-center text-[10px] font-mono uppercase tracking-[0.16em] text-[#5C564E] sm:hidden">
          {step === 'upload' && 'Bước 1 / 4 · Tải ảnh lên'}
          {step === 'processing' && 'Bước 2 / 4 · AI phân tích'}
          {step === 'review' && 'Bước 3 / 4 · Kiểm duyệt & lưu'}
          {step === 'confirmed' && 'Bước 4 / 4 · Hoàn tất'}
          {step === 'failed' && 'Quá trình số hóa cần thử lại'}
        </p>
      </div>

      {/* Global Error Banner */}
      {errorMessage && (
        <div className="mb-6 p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-900 text-sm flex items-start gap-3 shadow-2xs">
          <svg className="w-5 h-5 flex-shrink-0 text-rose-500 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <div className="flex-1">
            <p className="font-semibold text-xs uppercase font-mono tracking-wider text-rose-800">Đã xảy ra sự cố</p>
            <p className="mt-0.5 text-xs">{errorMessage}</p>
          </div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="text-rose-500 hover:text-rose-700 font-bold text-xs"
          >
            ✕
          </button>
        </div>
      )}

      {/* STEP 1: UPLOAD */}
      {step === 'upload' && (
        <UploadDropzone onUpload={handleUpload} isUploading={isUploading} />
      )}

      {/* STEP 2: PROCESSING */}
      {step === 'processing' && (
        <div className="double-bezel-shell max-w-md mx-auto">
          <div className="double-bezel-core p-10 text-center border border-[#E8E5DE]">
            <div className="relative w-20 h-20 mx-auto mb-6">
              <div className="w-20 h-20 rounded-full border-4 border-[#E8E5DE] border-t-[#9C5234] animate-spin flex items-center justify-center shadow-xs">
                <svg className="w-8 h-8 text-[#9C5234]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
            </div>
            <h3 className="font-serif text-2xl font-normal text-[#1A1918]">AI Đang Phân Tích Trang Phục</h3>
            <p className="text-xs sm:text-sm text-[#5C564E] mt-2 leading-relaxed">
              Đang trích xuất các vùng trang phục, cắt hình và nhận diện chất liệu, kiểu dáng, phong cách...
            </p>
            <div className="mt-6 inline-flex items-center gap-2 text-xs font-mono text-[#736E65] bg-[#FAF8F5] py-1.5 px-4 rounded-full border border-[#E8E5DE]">
              <span className="w-2 h-2 rounded-full bg-[#9C5234] animate-pulse"></span>
              <span>Đang chuẩn bị ảnh và thông tin món đồ</span>
            </div>
          </div>
        </div>
      )}

      {/* STEP 3: REVIEW */}
      {step === 'review' && taxonomyError && <p role="alert" className="text-sm text-[#9C5234]">Chưa tải được danh mục. <button type="button" onClick={retryTaxonomy} className="underline">Thử lại</button></p>}
      {step === 'review' && batchReview && (
        <div className="space-y-6">
          {/* Top Review Bar */}
          <div className="flex flex-wrap items-center justify-between gap-4 p-5 bg-white rounded-3xl shadow-2xs border border-[#E8E5DE]">
            <div>
              <h2 className="font-serif text-xl font-medium text-[#1A1918] flex items-center gap-2.5">
                <span>Trang phục tìm thấy ({batchReview.detections.length} món đồ)</span>
                <span className="text-[10px] font-mono uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-[#9C5234]/10 text-[#9C5234] border border-[#9C5234]/20 font-semibold">
                  {needsReviewCount > 0 ? `${needsReviewCount} món cần xem lại` : 'Sẵn sàng lưu'}
                </span>
              </h2>

            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleCancelBatch}
                disabled={isCancelling || isConfirming || isCropSaving}
                className="tactile-btn px-4 py-2 text-xs font-mono uppercase tracking-wider text-[#736E65] hover:text-rose-600 bg-[#FAF8F5] hover:bg-rose-50 border border-[#E8E5DE] rounded-full transition flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                {isCancelling ? 'Đang hủy...' : 'Hủy bỏ đợt này'}
              </button>
            </div>
          </div>

          {batchReview.show_review_hint && (
            <p role="note" className="rounded-2xl bg-[#F5F2EC] px-5 py-4 text-sm text-[#5C564E]">
              Chọn những món muốn giữ, kiểm tra loại và màu. Bạn có thể sửa vùng cắt hoặc mở Chi tiết bổ sung khi cần.
            </p>
          )}
          {/* Quality Warnings Banner */}
          {batchReview.quality_warnings.length > 0 && (
            <div className="p-4 sm:p-5 rounded-2xl bg-amber-50 border border-amber-300 text-amber-950 text-sm shadow-2xs flex items-start gap-3.5">
              <svg className="w-5 h-5 flex-shrink-0 text-amber-700 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <div>
                <p className="font-semibold text-xs sm:text-sm font-mono uppercase tracking-wider text-amber-900">Lưu ý chất lượng ảnh:</p>
                <p className="mt-1 text-sm">Một số ảnh chưa được nhận diện đầy đủ. Kiểm tra vùng cắt và loại món trước khi lưu.</p>
              </div>
            </div>
          )}

          {sources.length > 0 && (
            <div className="flex gap-3 overflow-x-auto pb-2" aria-label="Ảnh đã tải lên">
              {batchReview.detections.some((det) => !det.source_media_asset_id) && (
                <button type="button" aria-pressed={selectedSourceId === 'unassigned'}
                  onClick={() => { setSelectedSourceId('unassigned'); setSelectedDetectionId(null); }}
                  className="shrink-0 rounded-xl border p-2 text-sm">Món chưa xác định ảnh</button>
              )}
              {sources.map((entry, index) => {
                const preview = batchReview.detections.find((det) => det.source_media_asset_id === entry.media_asset_id)?.crop_url;
                return (
                <button key={entry.media_asset_id} type="button"
                  aria-pressed={source?.media_asset_id === entry.media_asset_id}
                  onClick={() => {
                    setSelectedSourceId(entry.media_asset_id);
                    setSelectedDetectionId(batchReview.detections.find(
                      (det) => det.source_media_asset_id === entry.media_asset_id)?.detection_id ?? null);
                  }} className="shrink-0 rounded-xl border border-[#D5D1C7] p-2 aria-pressed:border-[#9C5234] aria-pressed:bg-[#F5F2EC]">
                  {preview && (
                    <PrivateMediaImage source={preview}
                      alt={`Ảnh ${index + 1}`} className="h-16 w-20 object-contain" />
                  )}
                  <span className="text-xs">Ảnh {index + 1} / {sources.length}</span>
                </button>
                );
              })}
            </div>
          )}
          <div className="mx-auto max-w-4xl space-y-5">
              {visibleDetections.map((det, idx) => (
                <DetectionItemCard
                  taxonomy={taxonomy}
                  key={det.detection_id}
                  detection={det}
                  index={idx}
                  isSelected={selectedDetectionId === det.detection_id}
                  accepted={!!acceptedDetections[det.detection_id]}
                  attributes={editedAttributes[det.detection_id] || det.attributes}
                  onSelect={() => setSelectedDetectionId(det.detection_id)}
                  onToggleAccepted={(acc) => handleToggleAccepted(det.detection_id, acc)}
                  onUpdateAttribute={(k, v) => handleUpdateAttribute(det.detection_id, k, v)}
                  cropEditor={source && batchId && det.source_media_asset_id === source.media_asset_id ? (
                    <CropEditor key={det.crop_url} source={source.media_url}
                      initialBox={det.bounding_box} rawBox={det.raw_bounding_box}
                      disabled={isCropSaving || isConfirming || isCancelling}
                      onSave={async (box) => {
                        setIsCropSaving(true);
                        try {
                          setBatchReview(await updateDetectionCrop(batchId, det.detection_id, box));
                        } finally { setIsCropSaving(false); }
                      }} />
                  ) : undefined}
                />
              ))}
          </div>

          {/* Save action stays in document flow so crop controls remain unobstructed. */}
          <div className="relative p-4 sm:p-5 bg-[#1A1918]/92 backdrop-blur-xl rounded-2xl shadow-xl border border-white/10 text-[#FBFBF9] flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="w-2.5 h-2.5 rounded-full bg-[#9C5234] animate-pulse"></span>
              <span className="text-xs font-mono text-[#D5D1C7]">
                Đã chọn <strong className="text-white font-bold">{acceptedCount}</strong> /{' '}
                {batchReview.detections.length} món đồ để thêm vào tủ đồ.
              </span>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleCancelBatch}
                disabled={isCancelling || isConfirming || isCropSaving}
                className="px-4 py-2 text-xs font-mono uppercase tracking-wider text-[#D5D1C7] hover:text-white transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Hủy bỏ
              </button>
              <button
                type="button"
                onClick={handleConfirmBatch}
                disabled={isConfirming || isCancelling || isCropSaving || acceptedCount === 0}
                className={`tactile-btn px-6 py-2.5 rounded-full font-mono text-xs uppercase tracking-wider text-white shadow-sm transition-all flex items-center gap-2 ${
                  isConfirming || isCancelling || isCropSaving || acceptedCount === 0
                    ? 'bg-white/15 text-white/40 cursor-not-allowed'
                    : 'bg-[#9C5234] hover:bg-[#854329] active:scale-95'
                }`}
              >
                {isConfirming ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span>Đang lưu vào tủ đồ...</span>
                  </>
                ) : (
                  <>
                    <span>✓ Lưu vào tủ đồ ({acceptedCount})</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* STEP 4: CONFIRMED */}
      {step === 'confirmed' && (
        <div className="double-bezel-shell max-w-lg mx-auto">
          <div className="double-bezel-core p-8 sm:p-10 text-center border border-[#E8E5DE]">
            <div className="w-16 h-16 rounded-full bg-[#9C5234]/10 text-[#9C5234] mx-auto flex items-center justify-center shadow-2xs mb-5">
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h3 className="font-serif text-2xl sm:text-3xl font-normal text-[#1A1918]">Số Hóa Thành Công!</h3>
            <p className="text-xs sm:text-sm text-[#5C564E] mt-2.5 leading-relaxed">
              Đã thêm thành công <strong className="text-[#9C5234]">{confirmedItemIds.length}</strong> món đồ mới vào tủ đồ của bạn với đầy đủ ảnh crop và thông tin phong cách.
            </p>

            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
              <button
                type="button"
                onClick={handleReset}
                className="tactile-btn w-full sm:w-auto px-5 py-2.5 rounded-full font-mono text-xs uppercase tracking-wider text-[#1A1918] bg-white border border-[#D5D1C7] hover:bg-[#FAF8F5] transition shadow-2xs"
              >
                + Số hóa thêm món khác
              </button>
              <a
                href="/wardrobe"
                className="tactile-btn w-full sm:w-auto px-6 py-2.5 rounded-full font-mono text-xs uppercase tracking-wider text-white bg-[#1A1918] hover:bg-[#2D2420] transition shadow-xs inline-block"
              >
                Xem tủ đồ cá nhân →
              </a>
            </div>
          </div>
        </div>
      )}

      {/* STEP 5: FAILED */}
      {step === 'failed' && (
        <div className="double-bezel-shell max-w-md mx-auto">
          <div className="double-bezel-core p-8 text-center border border-[#E8E5DE]">
            <div className="w-16 h-16 rounded-full bg-rose-50 text-rose-600 mx-auto flex items-center justify-center shadow-2xs mb-4">
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h3 className="font-serif text-2xl font-normal text-[#1A1918]">Không Thể Hoàn Tất Số Hóa</h3>
            {batchId && !batchReview && <button type="button" className="mt-4 rounded-lg border px-4 py-2 text-sm"
              onClick={() => { setErrorMessage(null); setStep('processing'); }}>Tiếp tục kiểm tra kết quả</button>}
            <p className="text-xs sm:text-sm text-[#5C564E] mt-2 leading-relaxed">{errorMessage || 'Có lỗi xảy ra trong quá trình phân tích.'}</p>
            <button
              type="button"
              onClick={handleReset}
              className="tactile-btn mt-6 px-6 py-2.5 rounded-full font-mono text-xs uppercase tracking-wider text-white bg-[#1A1918] hover:bg-[#2D2420] transition shadow-xs"
            >
              Thử lại với ảnh khác
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
