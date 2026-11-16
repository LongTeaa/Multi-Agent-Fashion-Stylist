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
import { AlertIcon, CheckIcon, CloseIcon, Spinner, TrashIcon } from '@/components/ui/icons';

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
          const sourcesWithValidCategory = new Set(
            review.detections
              .filter(
                (det) =>
                  det.source_media_asset_id &&
                  det.attributes?.category &&
                  det.attributes.category !== 'unknown'
              )
              .map((det) => det.source_media_asset_id)
          );
          for (const det of review.detections) {
            const isUnknownCat =
              !det.attributes?.category || det.attributes.category === 'unknown';
            const hasValidSiblingOnSameSource =
              !!det.source_media_asset_id &&
              sourcesWithValidCategory.has(det.source_media_asset_id);
            acceptedMap[det.detection_id] = !(isUnknownCat && hasValidSiblingOnSameSource);
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
    const invalidDetection = batchReview.detections.find((det) => {
      const isAccepted = !!acceptedDetections[det.detection_id];
      if (!isAccepted) return false;
      const attrs = editedAttributes[det.detection_id] || det.attributes;
      return !attrs?.category || attrs.category === 'unknown';
    });

    if (invalidDetection) {
      if (
        invalidDetection.source_media_asset_id &&
        invalidDetection.source_media_asset_id !== selectedSourceId
      ) {
        setSelectedSourceId(invalidDetection.source_media_asset_id);
      }
      setSelectedDetectionId(invalidDetection.detection_id);
      setErrorMessage(
        'Vui lòng chọn danh mục chính hợp lệ cho tất cả các món đồ được chọn lưu trước khi xác nhận.'
      );
      return;
    }

    setIsConfirming(true);
    setErrorMessage(null);

    const confirmations = batchReview.detections.map((det) => {
      const isAccepted = !!acceptedDetections[det.detection_id];
      return {
        detection_id: det.detection_id,
        accepted: isAccepted,
        custom_attributes: isAccepted
          ? editedAttributes[det.detection_id] || det.attributes
          : undefined,
      };
    });

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
      'Hủy lượt thêm đồ này? Ảnh vừa tải lên và kết quả nhận diện sẽ bị xóa.'
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

  const stepIndex = step === 'upload' ? 0 : step === 'processing' ? 1 : step === 'failed' ? -1 : 2;
  const busy = isConfirming || isCancelling || isCropSaving;

  return (
    <div className="w-full">
      {/* Step tracker */}
      {step !== 'failed' && step !== 'confirmed' && (
        <ol className="mx-auto mb-8 flex max-w-xl items-center gap-2 text-sm" aria-label="Các bước thêm đồ">
          {['Chọn ảnh', 'Nhận diện', 'Kiểm tra & lưu'].map((label, idx) => {
            const isCurrent = idx === stepIndex;
            const isDone = idx < stepIndex;
            return (
              <React.Fragment key={label}>
                {idx > 0 && <li aria-hidden="true" className={`h-px flex-1 ${isDone || isCurrent ? 'bg-ink' : 'bg-line-strong'}`} />}
                <li
                  aria-current={isCurrent ? 'step' : undefined}
                  className={`flex shrink-0 items-center gap-2 ${isCurrent ? 'font-semibold text-ink' : isDone ? 'text-ink-2' : 'text-muted'}`}
                >
                  <span
                    className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                      isCurrent ? 'bg-ink text-paper' : isDone ? 'bg-accent text-white' : 'border border-line-strong'
                    }`}
                  >
                    {isDone ? <CheckIcon size={13} /> : idx + 1}
                  </span>
                  <span className={isCurrent ? '' : 'hidden sm:inline'}>{label}</span>
                </li>
              </React.Fragment>
            );
          })}
        </ol>
      )}

      {errorMessage && step !== 'failed' && (
        <div role="alert" className="notice notice-danger mb-6">
          <AlertIcon size={18} className="mt-0.5 shrink-0" />
          <p className="flex-1">{errorMessage}</p>
          <button type="button" onClick={() => setErrorMessage(null)} aria-label="Đóng thông báo lỗi" className="shrink-0">
            <CloseIcon size={14} />
          </button>
        </div>
      )}

      {/* STEP 1: UPLOAD */}
      {step === 'upload' && <UploadDropzone onUpload={handleUpload} isUploading={isUploading} />}

      {/* STEP 2: PROCESSING */}
      {step === 'processing' && (
        <div role="status" className="card mx-auto max-w-md px-8 py-12 text-center">
          <Spinner size={36} className="mx-auto text-accent" />
          <h2 className="display mt-6 text-2xl">Đang nhận diện món đồ</h2>
          <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
            Tách từng món trong ảnh và đoán loại, màu, chất liệu. Thường mất vài giây.
          </p>
        </div>
      )}

      {/* STEP 3: REVIEW */}
      {step === 'review' && taxonomyError && (
        <p role="alert" className="mb-4 text-sm text-danger">
          Chưa tải được danh mục.{' '}
          <button type="button" onClick={retryTaxonomy} className="font-semibold underline">
            Thử lại
          </button>
        </p>
      )}
      {step === 'review' && batchReview && (
        <div className="mx-auto max-w-4xl space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="display text-[1.75rem]">Kiểm tra trước khi lưu</h2>
              <p className="mt-1 text-sm text-ink-2">
                Tìm thấy {batchReview.detections.length} món
                {needsReviewCount > 0 ? (
                  <>
                    {' · '}
                    <span className="font-semibold text-warning">{needsReviewCount} món cần xem lại</span>
                  </>
                ) : (
                  ' · Sẵn sàng lưu'
                )}
              </p>
            </div>
            <button type="button" onClick={handleCancelBatch} disabled={busy} className="btn btn-ghost btn-sm">
              <TrashIcon size={15} />
              {isCancelling ? 'Đang hủy…' : 'Hủy lượt này'}
            </button>
          </div>

          {batchReview.show_review_hint && (
            <p role="note" className="notice notice-info">
              Chọn những món muốn giữ, kiểm tra loại và màu. Bạn có thể sửa vùng cắt hoặc mở Chi tiết bổ sung khi cần.
            </p>
          )}

          {batchReview.quality_warnings.length > 0 && (
            <div className="notice notice-warning">
              <AlertIcon size={18} className="mt-0.5 shrink-0" />
              <p>Một số ảnh chưa được nhận diện đầy đủ. Kiểm tra vùng cắt và loại món trước khi lưu.</p>
            </div>
          )}

          {sources.length > 0 && (
            <div className="-mx-4 flex gap-2.5 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0" aria-label="Ảnh đã tải lên">
              {batchReview.detections.some((det) => !det.source_media_asset_id) && (
                <button
                  type="button"
                  aria-pressed={selectedSourceId === 'unassigned'}
                  onClick={() => {
                    setSelectedSourceId('unassigned');
                    setSelectedDetectionId(null);
                  }}
                  className="chip shrink-0"
                >
                  Món chưa xác định ảnh
                </button>
              )}
              {sources.map((entry, index) => {
                const preview = batchReview.detections.find((det) => det.source_media_asset_id === entry.media_asset_id)?.crop_url;
                const isActive = source?.media_asset_id === entry.media_asset_id;
                return (
                  <button
                    key={entry.media_asset_id}
                    type="button"
                    aria-pressed={isActive}
                    onClick={() => {
                      setSelectedSourceId(entry.media_asset_id);
                      setSelectedDetectionId(
                        batchReview.detections.find((det) => det.source_media_asset_id === entry.media_asset_id)?.detection_id ?? null
                      );
                    }}
                    className={`flex shrink-0 flex-col items-center gap-1 rounded-xl border p-1.5 text-xs transition-colors ${
                      isActive ? 'border-ink bg-surface text-ink' : 'border-line bg-surface text-muted hover:border-line-strong'
                    }`}
                  >
                    {preview && (
                      <PrivateMediaImage source={preview} alt={`Ảnh ${index + 1}`} className="h-16 w-20 rounded-lg bg-sunken object-contain" />
                    )}
                    <span>
                      Ảnh {index + 1} / {sources.length}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          <div className="space-y-4">
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
                cropEditor={
                  source && batchId && det.source_media_asset_id === source.media_asset_id ? (
                    <CropEditor
                      key={det.crop_url}
                      source={source.media_url}
                      initialBox={det.bounding_box}
                      rawBox={det.raw_bounding_box}
                      disabled={busy}
                      onSave={async (box) => {
                        setIsCropSaving(true);
                        try {
                          setBatchReview(await updateDetectionCrop(batchId, det.detection_id, box));
                        } finally {
                          setIsCropSaving(false);
                        }
                      }}
                    />
                  ) : undefined
                }
              />
            ))}
          </div>

          {/* Save action stays in document flow so crop controls remain unobstructed. */}
          <div className="card flex flex-wrap items-center justify-between gap-3 p-4 sm:px-5">
            <p className="text-sm text-ink-2">
              Đã chọn <strong className="text-ink">{acceptedCount}</strong> / {batchReview.detections.length} món
            </p>
            <button
              type="button"
              onClick={handleConfirmBatch}
              disabled={busy || acceptedCount === 0}
              className="btn btn-primary"
            >
              {isConfirming ? (
                <>
                  <Spinner size={15} />
                  Đang lưu vào tủ đồ…
                </>
              ) : (
                <>
                  <CheckIcon size={16} />
                  Lưu vào tủ đồ ({acceptedCount})
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* STEP 4: CONFIRMED (only visible when no onFinish handler takes over) */}
      {step === 'confirmed' && (
        <div className="card mx-auto max-w-md px-8 py-12 text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-success-soft text-success">
            <CheckIcon size={24} />
          </span>
          <h2 className="display mt-5 text-2xl">Đã thêm vào tủ đồ</h2>
          <p className="mt-2 text-[0.9375rem] text-ink-2">
            {confirmedItemIds.length} món mới đã sẵn sàng để phối.
          </p>
          <div className="mt-7 flex flex-col justify-center gap-2 sm:flex-row">
            <button type="button" onClick={handleReset} className="btn btn-secondary">
              Thêm món khác
            </button>
            <a href="/wardrobe" className="btn btn-primary">
              Xem tủ đồ
            </a>
          </div>
        </div>
      )}

      {/* FAILED */}
      {step === 'failed' && (
        <div role="alert" className="card mx-auto max-w-md px-8 py-12 text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft text-danger">
            <AlertIcon size={24} />
          </span>
          <h2 className="display mt-5 text-2xl">Chưa thể hoàn tất</h2>
          <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
            {errorMessage || 'Có lỗi xảy ra trong quá trình nhận diện.'}
          </p>
          <div className="mt-7 flex flex-col justify-center gap-2 sm:flex-row">
            {batchId && !batchReview && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setErrorMessage(null);
                  setStep('processing');
                }}
              >
                Tiếp tục kiểm tra kết quả
              </button>
            )}
            <button type="button" onClick={handleReset} className="btn btn-primary">
              Thử lại với ảnh khác
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
