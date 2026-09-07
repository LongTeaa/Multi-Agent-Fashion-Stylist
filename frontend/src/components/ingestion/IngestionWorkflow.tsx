'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import type {
  FashionAttributes,
  IngestionBatchReviewResponse,
} from '@/types/ingestion';
import {
  uploadIngestionImages,
  getIngestionBatch,
  confirmIngestionBatch,
  deleteIngestionBatch,
} from '@/lib/api';
import { UploadDropzone } from './UploadDropzone';
import { BoundingBoxOverlay } from './BoundingBoxOverlay';
import { DetectionItemCard } from './DetectionItemCard';

type WorkflowStep = 'upload' | 'processing' | 'review' | 'confirmed' | 'failed';

interface IngestionWorkflowProps {
  onFinish?: (createdItemIds: string[]) => void;
}

export function IngestionWorkflow({ onFinish }: IngestionWorkflowProps) {
  const [step, setStep] = useState<WorkflowStep>('upload');
  const [isUploading, setIsUploading] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batchReview, setBatchReview] = useState<IngestionBatchReviewResponse | null>(null);
  const [uploadedPreviewUrl, setUploadedPreviewUrl] = useState<string | undefined>(undefined);
  const [selectedDetectionId, setSelectedDetectionId] = useState<string | null>(null);
  const [acceptedDetections, setAcceptedDetections] = useState<Record<string, boolean>>({});
  const [editedAttributes, setEditedAttributes] = useState<Record<string, FashionAttributes>>({});
  const [confirmedItemIds, setConfirmedItemIds] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Clean up polling timer
  useEffect(() => {
    return () => {
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current);
      }
    };
  }, []);

  // Poll for batch status until ready or failed
  const startPollingBatch = useCallback((id: string) => {
    let attempts = 0;
    const maxAttempts = 30; // 45 seconds total

    if (pollingTimerRef.current) {
      clearInterval(pollingTimerRef.current);
    }

    const poll = async () => {
      attempts += 1;
      try {
        const review = await getIngestionBatch(id);
        if (review.status === 'needs_review') {
          if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
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
            setSelectedDetectionId(review.detections[0].detection_id);
          }
          setStep('review');
        } else if (review.status === 'failed') {
          if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
          setErrorMessage(
            review.quality_warnings.join('; ') || 'AI không thể phân tích ảnh này. Vui lòng thử lại.'
          );
          setStep('failed');
        } else if (attempts >= maxAttempts) {
          if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
          setErrorMessage('Quá trình xử lý ảnh mất quá nhiều thời gian. Vui lòng thử lại sau.');
          setStep('failed');
        }
      } catch (err: unknown) {
        if (attempts >= 5) {
          if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
          setErrorMessage((err as Error).message || 'Không thể lấy thông tin kết quả phân tích.');
          setStep('failed');
        }
      }
    };

    // Run first check immediately, then poll every 1.5s
    poll();
    pollingTimerRef.current = setInterval(poll, 1500);
  }, []);

  const handleUpload = async (files: File[], declaredKind?: string) => {
    setIsUploading(true);
    setErrorMessage(null);
    try {
      // Keep preview of first uploaded image for bounding box display
      if (files.length > 0) {
        setUploadedPreviewUrl(URL.createObjectURL(files[0]));
      }

      const res = await uploadIngestionImages(files, declaredKind);
      setBatchId(res.batch_id);
      setStep('processing');
      startPollingBatch(res.batch_id);
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
    if (!batchId || !batchReview) return;

    setIsConfirming(true);
    setErrorMessage(null);

    const confirmations = batchReview.detections.map((det) => ({
      detection_id: det.detection_id,
      accepted: !!acceptedDetections[det.detection_id],
      custom_attributes: editedAttributes[det.detection_id] || det.attributes,
    }));

    try {
      const res = await confirmIngestionBatch(batchId, {
        idempotency_token: crypto.randomUUID(),
        confirmations,
      });

      setConfirmedItemIds(res.wardrobe_item_ids);
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
    if (!batchId) {
      handleReset();
      return;
    }

    const confirmed = window.confirm(
      'Bạn có chắc chắn muốn hủy bỏ lượt tải lên này? Toàn bộ ảnh tạm và phân tích AI sẽ bị xóa sạch.'
    );
    if (!confirmed) return;

    setIsCancelling(true);
    try {
      await deleteIngestionBatch(batchId);
    } catch {
      // Ignore cleanup error if already deleted
    } finally {
      setIsCancelling(false);
      handleReset();
    }
  };

  const handleReset = () => {
    if (uploadedPreviewUrl) {
      URL.revokeObjectURL(uploadedPreviewUrl);
    }
    setStep('upload');
    setBatchId(null);
    setBatchReview(null);
    setUploadedPreviewUrl(undefined);
    setSelectedDetectionId(null);
    setAcceptedDetections({});
    setEditedAttributes({});
    setConfirmedItemIds([]);
    setErrorMessage(null);
  };

  const acceptedCount = Object.values(acceptedDetections).filter(Boolean).length;

  return (
    <div className="w-full max-w-6xl mx-auto px-4 py-8">
      {/* Step Tracker */}
      <div className="mb-8">
        <div className="flex items-center justify-center max-w-2xl mx-auto">
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
                    className={`flex-1 h-1 transition-colors ${
                      isCompleted ? 'bg-indigo-600' : 'bg-slate-200'
                    }`}
                  />
                )}
                <div className="flex flex-col items-center">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                      isCompleted
                        ? 'bg-indigo-600 text-white'
                        : isCurrent
                        ? 'bg-indigo-600 text-white ring-4 ring-indigo-100 scale-110'
                        : 'bg-slate-200 text-slate-500'
                    }`}
                  >
                    {isCompleted ? '✓' : idx + 1}
                  </div>
                  <span
                    className={`text-[11px] font-medium mt-1.5 whitespace-nowrap ${
                      isCurrent ? 'text-indigo-600 font-bold' : 'text-slate-500'
                    }`}
                  >
                    {s.label}
                  </span>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Global Error Banner */}
      {errorMessage && (
        <div className="mb-6 p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-sm flex items-start gap-3 shadow-sm">
          <svg className="w-5 h-5 flex-shrink-0 text-rose-500 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <div className="flex-1">
            <p className="font-semibold">Đã xảy ra sự cố</p>
            <p>{errorMessage}</p>
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
        <div className="max-w-md mx-auto p-10 bg-white rounded-2xl shadow-xl border border-slate-200 text-center">
          <div className="relative w-20 h-20 mx-auto mb-6">
            <div className="absolute inset-0 rounded-full border-4 border-indigo-100 animate-ping opacity-75"></div>
            <div className="w-20 h-20 rounded-full border-4 border-indigo-600 border-t-transparent animate-spin flex items-center justify-center shadow-md">
              <svg className="w-8 h-8 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
          </div>
          <h3 className="text-xl font-bold text-slate-800">AI Đang Phân Tích Trang Phục</h3>
          <p className="text-sm text-slate-600 mt-2">
            Đang trích xuất các vùng trang phục, cắt hình và nhận diện chất liệu, kiểu dáng, phong cách...
          </p>
          <div className="mt-6 flex justify-center items-center gap-2 text-xs text-indigo-600 font-medium bg-indigo-50/80 py-2 px-4 rounded-full border border-indigo-100">
            <span className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse"></span>
            <span>Mã phiên tải: {batchId?.slice(0, 8)}</span>
          </div>
        </div>
      )}

      {/* STEP 3: REVIEW */}
      {step === 'review' && batchReview && (
        <div className="space-y-6">
          {/* Top Review Bar */}
          <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-white rounded-2xl shadow-sm border border-slate-200">
            <div>
              <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                <span>Kết Quả Phát Hiện ({batchReview.detections.length} món đồ)</span>
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-medium">
                  Cần kiểm tra
                </span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Ngữ cảnh ảnh: <span className="font-semibold text-slate-700">{batchReview.input_kind}</span> • Hãy kiểm tra các trường được đánh dấu trước khi lưu.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleCancelBatch}
                disabled={isCancelling}
                className="px-4 py-2 text-xs font-semibold text-rose-600 bg-rose-50 hover:bg-rose-100 rounded-xl transition flex items-center gap-1.5"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                {isCancelling ? 'Đang hủy...' : 'Hủy bỏ đợt này'}
              </button>
            </div>
          </div>

          {/* Quality Warnings Banner */}
          {batchReview.quality_warnings.length > 0 && (
            <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 text-sm shadow-sm flex items-start gap-3">
              <svg className="w-5 h-5 flex-shrink-0 text-amber-600 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <div>
                <p className="font-semibold">Lưu ý chất lượng ảnh:</p>
                <ul className="list-disc list-inside mt-1 text-xs space-y-0.5 text-amber-800">
                  {batchReview.quality_warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* 2-Column Inspector Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left: Original Photo with Bounding Boxes */}
            <div className="lg:col-span-5 lg:sticky lg:top-6">
              <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-200">
                <h3 className="text-sm font-bold text-slate-800 mb-3 flex items-center justify-between">
                  <span>Ảnh Gốc & Vị Trí Nhận Diện</span>
                  <span className="text-xs text-indigo-600 font-normal">Tự động gắn khung</span>
                </h3>
                <BoundingBoxOverlay
                  imageUrl={uploadedPreviewUrl}
                  detections={batchReview.detections}
                  selectedDetectionId={selectedDetectionId}
                  onSelectDetection={setSelectedDetectionId}
                />
              </div>
            </div>

            {/* Right: Detected Item Cards */}
            <div className="lg:col-span-7 space-y-4">
              {batchReview.detections.map((det, idx) => (
                <DetectionItemCard
                  key={det.detection_id}
                  detection={det}
                  index={idx}
                  isSelected={selectedDetectionId === det.detection_id}
                  accepted={!!acceptedDetections[det.detection_id]}
                  attributes={editedAttributes[det.detection_id] || det.attributes}
                  onSelect={() => setSelectedDetectionId(det.detection_id)}
                  onToggleAccepted={(acc) => handleToggleAccepted(det.detection_id, acc)}
                  onUpdateAttribute={(k, v) => handleUpdateAttribute(det.detection_id, k, v)}
                />
              ))}
            </div>
          </div>

          {/* Sticky Bottom Action Bar */}
          <div className="sticky bottom-4 z-30 p-4 bg-slate-900/90 backdrop-blur-md rounded-2xl shadow-2xl border border-slate-800 text-white flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="w-3 h-3 rounded-full bg-emerald-400 animate-pulse"></span>
              <span className="text-sm">
                Đã chọn <strong className="text-indigo-400 font-bold">{acceptedCount}</strong> /{' '}
                {batchReview.detections.length} món đồ để thêm vào tủ đồ.
              </span>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleCancelBatch}
                disabled={isCancelling}
                className="px-4 py-2 text-xs text-slate-300 hover:text-white hover:bg-slate-800 rounded-xl transition"
              >
                Hủy bỏ
              </button>
              <button
                type="button"
                onClick={handleConfirmBatch}
                disabled={isConfirming || acceptedCount === 0}
                className={`px-6 py-2.5 rounded-xl font-medium text-white shadow-lg transition flex items-center gap-2 text-sm ${
                  isConfirming || acceptedCount === 0
                    ? 'bg-slate-700 cursor-not-allowed text-slate-400'
                    : 'bg-indigo-600 hover:bg-indigo-500 active:scale-95 shadow-indigo-500/30'
                }`}
              >
                {isConfirming ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Đang lưu vào tủ đồ...
                  </>
                ) : (
                  <>
                    <span>✓ Xác nhận lưu vào tủ đồ ({acceptedCount})</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* STEP 4: CONFIRMED */}
      {step === 'confirmed' && (
        <div className="max-w-lg mx-auto p-8 bg-white rounded-2xl shadow-xl border border-slate-200 text-center">
          <div className="w-16 h-16 rounded-full bg-emerald-100 text-emerald-600 mx-auto flex items-center justify-center shadow-inner mb-4">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h3 className="text-2xl font-bold text-slate-900">Số Hóa Thành Công!</h3>
          <p className="text-sm text-slate-600 mt-2">
            Đã thêm thành công <strong className="text-emerald-600">{confirmedItemIds.length}</strong> món đồ mới vào tủ đồ của bạn với đầy đủ ảnh crop và thông tin phong cách.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
            <button
              type="button"
              onClick={handleReset}
              className="w-full sm:w-auto px-5 py-2.5 rounded-xl font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 transition text-sm"
            >
              + Số hóa thêm món khác
            </button>
            <a
              href="/wardrobe"
              className="w-full sm:w-auto px-6 py-2.5 rounded-xl font-medium text-white bg-indigo-600 hover:bg-indigo-700 transition shadow-md shadow-indigo-100 text-sm inline-block"
            >
              Xem tủ đồ cá nhân →
            </a>
          </div>
        </div>
      )}

      {/* STEP 5: FAILED */}
      {step === 'failed' && (
        <div className="max-w-md mx-auto p-8 bg-white rounded-2xl shadow-xl border border-rose-200 text-center">
          <div className="w-16 h-16 rounded-full bg-rose-100 text-rose-600 mx-auto flex items-center justify-center shadow-inner mb-4">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h3 className="text-xl font-bold text-slate-900">Không Thể Hoàn Tất Số Hóa</h3>
          <p className="text-sm text-slate-600 mt-2">{errorMessage || 'Có lỗi xảy ra trong quá trình phân tích.'}</p>
          <button
            type="button"
            onClick={handleReset}
            className="mt-6 px-6 py-2.5 rounded-xl font-medium text-white bg-indigo-600 hover:bg-indigo-700 transition text-sm"
          >
            Thử lại với ảnh khác
          </button>
        </div>
      )}
    </div>
  );
}
