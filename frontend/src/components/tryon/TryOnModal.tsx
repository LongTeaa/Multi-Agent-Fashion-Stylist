'use client';

import React, { useCallback, useEffect, useId, useRef, useState } from 'react';

import {
  ApiError,
  createTryOn,
  deleteTryOnAvatar,
  listTryOnAvatars,
  recordOutfitWorn,
  setOutfitBookmark,
  uploadTryOnAvatar,
} from '@/lib/api';
import { PrivateMediaImage } from '@/components/media/PrivateMediaImage';
import type { TryOnAvatar, TryOnDisplayItem, TryOnResponseData } from '@/types/tryons';

const SLOT_NAMES: Record<string, string> = {
  top: 'Áo trong',
  bottom: 'Quần / Chân váy',
  dress: 'Đầm / Váy liền',
  footwear: 'Giày / Dép',
  outerwear: 'Áo khoác',
  accessory: 'Phụ kiện',
};

function createWearIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export interface TryOnModalProps {
  isOpen: boolean;
  outfitId: string;
  items: TryOnDisplayItem[];
  isBookmarked: boolean;
  isWorn?: boolean;
  onBookmarkChange: (outfitId: string, isBookmarked: boolean) => void;
  onWornChange?: (outfitId: string, isWorn: boolean, timesWorn?: number) => void;
  onClose: () => void;
}

export function TryOnModal({
  isOpen,
  outfitId,
  items,
  isBookmarked,
  isWorn = false,
  onBookmarkChange,
  onWornChange,
  onClose,
}: TryOnModalProps) {
  const [result, setResult] = useState<TryOnResponseData | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previousIsBookmarked, setPreviousIsBookmarked] = useState(isBookmarked);
  const [saved, setSaved] = useState(isBookmarked);
  const [isSaving, setIsSaving] = useState(false);
  const [previousIsWorn, setPreviousIsWorn] = useState(isWorn);
  const [worn, setWorn] = useState(isWorn);
  const [isRecordingWorn, setIsRecordingWorn] = useState(false);

  // Avatar state
  const [avatars, setAvatars] = useState<TryOnAvatar[]>([]);
  const [selectedAvatarId, setSelectedAvatarId] = useState<string>('preset-male');
  const [showOriginalAvatar, setShowOriginalAvatar] = useState<boolean>(false);

  // Outerwear vs Inner Top layering selection (if both exist)
  const hasTop = items.some((i) => i.slot === 'top');
  const hasOuterwear = items.some((i) => i.slot === 'outerwear');
  const hasBothTops = hasTop && hasOuterwear;
  const [selectedTopSlot, setSelectedTopSlot] = useState<'outerwear' | 'top'>('outerwear');

  // Avatar upload sub-dialog
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [consentChecked, setConsentChecked] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef<number>(0);
  const wearIdempotencyKeyRef = useRef<string>('');
  const itemsRef = useRef<TryOnDisplayItem[]>(items);
  const hasBothTopsRef = useRef<boolean>(hasBothTops);
  const selectedAvatarIdRef = useRef<string>(selectedAvatarId);
  const selectedTopSlotRef = useRef<'outerwear' | 'top'>(selectedTopSlot);
  const uploadInputId = useId();

  useEffect(() => {
    itemsRef.current = items;
    hasBothTopsRef.current = hasBothTops;
    selectedAvatarIdRef.current = selectedAvatarId;
    selectedTopSlotRef.current = selectedTopSlot;
  }, [hasBothTops, items, selectedAvatarId, selectedTopSlot]);

  // Load avatar presets and personal avatars
  const fetchAvatars = useCallback(async () => {
    try {
      const data = await listTryOnAvatars();
      if (Array.isArray(data) && data.length > 0) {
        setAvatars(data);
      }
    } catch {
      // Graceful fallback to default preset list if endpoint is offline
      setAvatars([
        {
          id: 'preset-male',
          name: 'Nam mẫu (Chuẩn)',
          is_preset: true,
          preset_gender: 'male',
          is_default: true,
          image_url: '/api/v1/tryons/presets/male',
          created_at: '2026-01-01T00:00:00Z',
        },
        {
          id: 'preset-female',
          name: 'Nữ mẫu (Chuẩn)',
          is_preset: true,
          preset_gender: 'female',
          is_default: false,
          image_url: '/api/v1/tryons/presets/female',
          created_at: '2026-01-01T00:00:00Z',
        },
      ]);
    }
  }, []);

  const generate = useCallback(
    async (avatarIdToUse?: string, topSlotToUse?: 'outerwear' | 'top') => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;

      requestIdRef.current += 1;
      const currentRequestId = requestIdRef.current;

      const activeAvatar = avatarIdToUse ?? selectedAvatarIdRef.current;
      const activeTopSlot = topSlotToUse ?? selectedTopSlotRef.current;
      const currentItems = itemsRef.current;
      const bothTopsPresent = hasBothTopsRef.current;

      // Filter items if layering choice is present
      const relevantItemIds = currentItems
        .filter((item) => {
          if (bothTopsPresent) {
            if (activeTopSlot === 'outerwear' && item.slot === 'top') return false;
            if (activeTopSlot === 'top' && item.slot === 'outerwear') return false;
          }
          return true;
        })
        .map((i) => i.id);

      setIsGenerating(true);
      setError(null);
      setShowOriginalAvatar(false);

      try {
        const res = await createTryOn(outfitId, {
          signal: controller.signal,
          avatarId: activeAvatar,
          itemIds: relevantItemIds,
        });
        if (requestIdRef.current === currentRequestId) {
          setResult(res);
        }
      } catch (requestError) {
        if (
          (requestError instanceof DOMException || requestError instanceof Error) &&
          requestError.name === 'AbortError'
        ) {
          return;
        }
        if (requestIdRef.current === currentRequestId) {
          setError(
            requestError instanceof ApiError
              ? requestError.message
              : 'Không thể tạo ảnh minh họa lúc này. Vui lòng thử lại.'
          );
        }
      } finally {
        if (requestIdRef.current === currentRequestId) {
          setIsGenerating(false);
        }
      }
    },
    [outfitId]
  );

  if (isBookmarked !== previousIsBookmarked) {
    setPreviousIsBookmarked(isBookmarked);
    setSaved(isBookmarked);
  }

  if (isWorn !== previousIsWorn) {
    setPreviousIsWorn(isWorn);
    setWorn(isWorn);
  }

  useEffect(() => {
    if (!isOpen) {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      return;
    }
    void fetchAvatars();
    const generationTask = window.setTimeout(() => void generate(), 0);
    return () => {
      window.clearTimeout(generationTask);
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, [fetchAvatars, generate, isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  const toggleBookmark = async () => {
    if (isSaving) return;
    const nextSaved = !saved;
    setIsSaving(true);
    setError(null);
    try {
      await setOutfitBookmark(outfitId, nextSaved);
      setSaved(nextSaved);
      onBookmarkChange(outfitId, nextSaved);
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : 'Không thể cập nhật trạng thái lưu. Vui lòng thử lại.'
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleRecordWorn = async () => {
    if (isRecordingWorn || worn) return;
    if (!wearIdempotencyKeyRef.current) {
      wearIdempotencyKeyRef.current = createWearIdempotencyKey();
    }
    setIsRecordingWorn(true);
    setError(null);
    try {
      const res = await recordOutfitWorn(outfitId, {
        idempotency_key: wearIdempotencyKeyRef.current,
      });
      wearIdempotencyKeyRef.current = createWearIdempotencyKey();
      setWorn(true);
      onWornChange?.(outfitId, true, res.times_worn);
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : 'Không thể ghi nhận trang phục đã mặc.'
      );
    } finally {
      setIsRecordingWorn(false);
    }
  };

  const handleSelectAvatar = (avatarId: string) => {
    setSelectedAvatarId(avatarId);
    void generate(avatarId);
  };

  const handleDeleteAvatar = async (avatarId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    try {
      await deleteTryOnAvatar(avatarId);
      setAvatars((prev) => prev.filter((a) => a.id !== avatarId));
      if (selectedAvatarId === avatarId) {
        setSelectedAvatarId('preset-male');
        void generate('preset-male');
      }
    } catch (delError) {
      setError(delError instanceof ApiError ? delError.message : 'Không thể xóa ảnh đại diện.');
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) {
      setUploadError('Vui lòng chọn một tệp ảnh.');
      return;
    }
    if (!consentChecked) {
      setUploadError('Vui lòng đồng ý điều khoản bảo mật ảnh trước khi tải lên.');
      return;
    }
    setIsUploading(true);
    setUploadError(null);
    try {
      const newAvatar = await uploadTryOnAvatar(uploadFile, uploadName.trim() || undefined);
      setAvatars((prev) => [...prev, newAvatar]);
      setSelectedAvatarId(newAvatar.id);
      setIsUploadOpen(false);
      setUploadFile(null);
      setUploadName('');
      void generate(newAvatar.id);
    } catch (err) {
      setUploadError(
        err instanceof ApiError ? err.message : 'Tải lên không thành công. Vui lòng thử lại.'
      );
    } finally {
      setIsUploading(false);
    }
  };

  if (!isOpen) return null;

  const currentAvatar = avatars.find((a) => a.id === selectedAvatarId);

  const renderLabel =
    result?.render_kind === 'virtual_tryon'
      ? 'Ảnh mặc thử AI'
      : result?.render_kind === 'moodboard'
      ? 'Moodboard dự phòng'
      : 'Ảnh minh họa AI';

  // Partition outfit items
  const garmentItems = items.filter((i) => ['top', 'bottom', 'dress', 'outerwear'].includes(i.slot));
  const coordinateItems = items.filter((i) => ['footwear', 'accessory'].includes(i.slot));

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-[#1A1918]/65 px-0 backdrop-blur-sm sm:items-center sm:px-5"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Xem trước bộ trang phục"
        className="max-h-[94dvh] w-full max-w-5xl overflow-y-auto rounded-t-[2rem] bg-[#E8E5DE] p-1.5 shadow-[0_24px_80px_rgba(42,34,29,0.28)] sm:rounded-[2rem]"
      >
        <div className="rounded-t-[calc(2rem-0.375rem)] bg-[#FBFBF9] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] sm:rounded-[calc(2rem-0.375rem)] sm:p-6">
          {/* Header */}
          <header className="flex items-start justify-between gap-5 pb-4">
            <div className="max-w-xl">
              <div className="flex items-center gap-2.5">
                <h2 className="font-serif text-2xl tracking-tight text-[#1A1918] sm:text-3xl">
                  Xem trước bộ trang phục
                </h2>
                <span className="rounded-full bg-[#EFECE6] px-2.5 py-0.5 text-xs font-semibold text-[#8B4513]">
                  2D Virtual Try-On
                </span>
              </div>
              <p className="mt-1 text-sm leading-relaxed text-[#5C564E]">
                Thử đồ trực quan trên người mẫu hoặc ảnh toàn thân của bạn. Không thay thế bảng size vật lý.
              </p>
            </div>
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              className="shrink-0 rounded-full bg-[#F1EEE8] px-4 py-2 text-xs font-semibold text-[#1A1918] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#E2DDD3] active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9C5234]"
            >
              Đóng
            </button>
          </header>

          {/* Avatar Selector Strip */}
          <div className="mb-4 rounded-2xl bg-[#F6F4EE] p-3 border border-[#E8E4DA]">
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-xs font-semibold text-[#1A1918] uppercase tracking-wider">
                Chọn người mẫu thử đồ:
              </span>
              <button
                type="button"
                onClick={() => setIsUploadOpen(!isUploadOpen)}
                className="text-xs font-medium text-[#9C5234] hover:underline"
              >
                {isUploadOpen ? '✕ Đóng tải ảnh' : '+ Tải ảnh toàn thân của bạn'}
              </button>
            </div>

            {/* Upload Drawer */}
            {isUploadOpen && (
              <form
                onSubmit={handleUploadSubmit}
                className="mb-3 rounded-xl bg-white p-3.5 border border-[#E0DACE] shadow-sm space-y-3"
              >
                <div className="flex flex-col sm:flex-row gap-3">
                  <div className="flex-1">
                    <label htmlFor={uploadInputId} className="block text-xs font-medium text-[#5C564E] mb-1">
                      Ảnh toàn thân (PNG/JPG/WEBP, &lt; 10MB)
                    </label>
                    <input
                      id={uploadInputId}
                      ref={fileInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                      className="block w-full text-xs text-[#5C564E] file:mr-3 file:py-1.5 file:px-3 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-[#F1EEE8] file:text-[#1A1918] hover:file:bg-[#E2DDD3]"
                    />
                  </div>
                  <div className="w-full sm:w-48">
                    <label className="block text-xs font-medium text-[#5C564E] mb-1">
                      Tên gợi nhớ (tùy chọn)
                    </label>
                    <input
                      type="text"
                      placeholder="Ảnh của tôi"
                      value={uploadName}
                      onChange={(e) => setUploadName(e.target.value)}
                      className="w-full rounded-lg border border-[#D5CFC4] px-2.5 py-1.5 text-xs text-[#1A1918] focus:border-[#9C5234] focus:outline-none"
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="consent_checkbox"
                    checked={consentChecked}
                    onChange={(e) => setConsentChecked(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-[#C8C2B7] text-[#9C5234] focus:ring-[#9C5234]"
                  />
                  <label htmlFor="consent_checkbox" className="text-xs text-[#736E65]">
                    Tôi đồng ý sử dụng ảnh chân dung để AI ghép đồ thử nghiệm và bảo mật trong tài khoản của tôi.
                  </label>
                </div>
                {uploadError && <p className="text-xs text-rose-700">{uploadError}</p>}
                <div className="flex justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => setIsUploadOpen(false)}
                    className="rounded-full px-3 py-1.5 text-xs font-semibold text-[#5C564E] hover:bg-[#F1EEE8]"
                  >
                    Hủy
                  </button>
                  <button
                    type="submit"
                    disabled={isUploading}
                    className="rounded-full bg-[#1A1918] px-4 py-1.5 text-xs font-semibold text-white hover:bg-[#302B27] disabled:opacity-50"
                  >
                    {isUploading ? 'Đang phân tích...' : 'Lưu & Mặc thử'}
                  </button>
                </div>
              </form>
            )}

            {/* Horizontal Avatars List */}
            <div className="flex items-center gap-2.5 overflow-x-auto pb-1">
              {avatars.map((avatar) => {
                const isSelected = avatar.id === selectedAvatarId;
                return (
                  <button
                    key={avatar.id}
                    type="button"
                    onClick={() => handleSelectAvatar(avatar.id)}
                    className={`relative flex items-center gap-2 rounded-xl px-3 py-1.5 text-xs font-medium transition duration-200 shrink-0 ${
                      isSelected
                        ? 'bg-[#1A1918] text-white shadow-sm ring-2 ring-[#9C5234]/40'
                        : 'bg-white text-[#4A453E] border border-[#DDD8CD] hover:border-[#B5AEA1]'
                    }`}
                  >
                    <span className="text-sm">{avatar.is_preset ? (avatar.preset_gender === 'female' ? '👩' : '👨') : '👤'}</span>
                    <span>{avatar.name}</span>
                    {!avatar.is_preset && (
                      <span
                        role="button"
                        title="Xóa avatar này"
                        onClick={(e) => handleDeleteAvatar(avatar.id, e)}
                        className="ml-1 text-xs opacity-60 hover:opacity-100 hover:text-rose-400"
                      >
                        ✕
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Main Content Grid */}
          <div className="grid grid-cols-1 gap-5 md:grid-cols-[minmax(0,1.35fr)_minmax(17rem,0.65fr)]">
            {/* Left: Try-On Image Canvas */}
            <div className="min-h-[26rem] overflow-hidden rounded-[1.5rem] bg-[#EEEAE2] p-1.5 flex flex-col">
              {/* Compare toggle bar */}
              {result && !isGenerating && currentAvatar && (
                <div className="mb-1.5 flex items-center justify-between px-2 pt-1">
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setShowOriginalAvatar(false)}
                      className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                        !showOriginalAvatar
                          ? 'bg-[#1A1918] text-white'
                          : 'bg-white/70 text-[#5C564E] hover:bg-white'
                      }`}
                    >
                      Kết quả mặc thử AI
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowOriginalAvatar(true)}
                      className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                        showOriginalAvatar
                          ? 'bg-[#1A1918] text-white'
                          : 'bg-white/70 text-[#5C564E] hover:bg-white'
                      }`}
                    >
                      Ảnh mẫu gốc (Trước khi mặc)
                    </button>
                  </div>
                  <span className="text-xs text-[#736E65] font-mono">
                    {(result.duration_ms / 1000).toFixed(1)}s
                  </span>
                </div>
              )}

              <div className="flex flex-1 min-h-[24rem] items-center justify-center overflow-hidden rounded-[calc(1.5rem-0.375rem)] bg-[#F5F2EC] relative">
                {isGenerating && (
                  <div role="status" className="w-full space-y-4 px-8 text-center max-w-sm">
                    <div className="mx-auto aspect-[3/4] w-full max-w-xs animate-pulse rounded-2xl bg-[#DDD7CD]" />
                    <p className="text-sm font-medium text-[#5C564E]">Đang tạo ảnh minh họa...</p>
                  </div>
                )}

                {!isGenerating && result && !showOriginalAvatar && (
                  <div className="relative w-full h-full flex flex-col items-center justify-center p-2">
                    <PrivateMediaImage
                      source={result.image_url}
                      alt={`${renderLabel} cho bộ trang phục`}
                      className="max-h-[64dvh] w-full object-contain rounded-xl"
                    />
                    {result.fallback_used && (
                      <div className="mt-2 max-w-md text-center rounded-xl bg-amber-50 p-2 text-xs text-amber-800 border border-amber-200">
                        AI khuếch tán đang bận hoặc quá hạn mức thử đồ trong ngày. Hệ thống hiển thị bảng phối đồ Moodboard dự phòng để bạn xem tổng thể.
                      </div>
                    )}
                  </div>
                )}

                {!isGenerating && showOriginalAvatar && currentAvatar && (
                  <div className="relative w-full h-full flex flex-col items-center justify-center p-2">
                    <PrivateMediaImage
                      source={currentAvatar.image_url}
                      alt={`Ảnh mẫu gốc ${currentAvatar.name}`}
                      className="max-h-[64dvh] w-full object-contain rounded-xl"
                    />
                    <span className="mt-2 text-xs text-[#736E65]">Người mẫu trước khi ướm đồ</span>
                  </div>
                )}

                {!isGenerating && !result && error && (
                  <div className="max-w-md px-8 py-14 text-center">
                    <p role="alert" className="text-sm leading-relaxed text-rose-800">{error}</p>
                    <button
                      type="button"
                      onClick={() => void generate()}
                      className="mt-5 rounded-full bg-[#1A1918] px-5 py-2.5 text-sm font-semibold text-[#FBFBF9] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#302B27] active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9C5234]"
                    >
                      Thử tạo lại
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Right: Outfit Items and Actions */}
            <aside className="flex flex-col rounded-[1.5rem] bg-white px-5 pb-5 pt-4 shadow-[0_14px_42px_rgba(85,68,55,0.08)]">
              {result && (
                <div className="mb-3 flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold text-[#9C5234]">
                    {renderLabel}
                  </span>
                </div>
              )}

              {/* Layering choice if top + outerwear exist */}
              {hasBothTops && (
                <div className="mb-3 rounded-xl bg-[#F7F5F0] p-2.5 border border-[#E5DFD3]">
                  <p className="text-xs font-semibold text-[#1A1918] mb-1.5">
                    Bộ đồ có cả áo khoác và áo trong:
                  </p>
                  <div className="grid grid-cols-2 gap-1.5">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedTopSlot('outerwear');
                        void generate(selectedAvatarId, 'outerwear');
                      }}
                      className={`rounded-lg py-1 px-2 text-xs font-semibold transition ${
                        selectedTopSlot === 'outerwear'
                          ? 'bg-[#1A1918] text-white'
                          : 'bg-white text-[#5C564E] hover:bg-[#EFECE5]'
                      }`}
                    >
                      Ướm áo khoác ngoài
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedTopSlot('top');
                        void generate(selectedAvatarId, 'top');
                      }}
                      className={`rounded-lg py-1 px-2 text-xs font-semibold transition ${
                        selectedTopSlot === 'top'
                          ? 'bg-[#1A1918] text-white'
                          : 'bg-white text-[#5C564E] hover:bg-[#EFECE5]'
                      }`}
                    >
                      Ướm áo trong
                    </button>
                  </div>
                </div>
              )}

              {/* Inpainted Garments */}
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[#736E65]">
                Trang phục ướm trên người
              </h3>
              <div className="mt-2 space-y-2">
                {garmentItems.map((item) => (
                  <div
                    key={item.id}
                    className="grid grid-cols-[2.75rem_1fr] items-center gap-3 rounded-2xl bg-[#F7F5F1] p-2"
                  >
                    <div className="h-11 w-11 overflow-hidden rounded-xl bg-[#E8E5DE]">
                      {item.imageUrl && (
                        <PrivateMediaImage
                          source={item.imageUrl}
                          alt={`Ảnh ${item.name}`}
                          className="h-full w-full object-cover"
                        />
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-xs font-medium text-[#1A1918]">{item.name}</p>
                      <p className="mt-0.5 text-[11px] text-[#736E65]">
                        {SLOT_NAMES[item.slot] ?? item.slot}
                        {item.primaryColor ? `, ${item.primaryColor}` : ''}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Coordinate Items (Footwear & Accessories) */}
              {coordinateItems.length > 0 && (
                <div className="mt-3.5 pt-3 border-t border-[#EFECE6]">
                  <div className="flex items-center justify-between mb-1.5">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-[#736E65]">
                      Phối kèm (Giày & Phụ kiện)
                    </h3>
                    <span className="text-[10px] text-[#9C5234] font-medium bg-[#F9F4F0] px-2 py-0.5 rounded-full">
                      Phối cùng bộ
                    </span>
                  </div>
                  <div className="space-y-2">
                    {coordinateItems.map((item) => (
                      <div
                        key={item.id}
                        className="grid grid-cols-[2.75rem_1fr] items-center gap-3 rounded-2xl bg-[#FDFBF7] border border-[#EBE6DC] p-2"
                      >
                        <div className="h-11 w-11 overflow-hidden rounded-xl bg-[#E8E5DE]">
                          {item.imageUrl && (
                            <PrivateMediaImage
                              source={item.imageUrl}
                              alt={`Ảnh ${item.name}`}
                              className="h-full w-full object-cover"
                            />
                          )}
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-xs font-medium text-[#1A1918]">{item.name}</p>
                          <p className="mt-0.5 text-[11px] text-[#736E65]">
                            {SLOT_NAMES[item.slot] ?? item.slot}
                            {item.primaryColor ? `, ${item.primaryColor}` : ''}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {error && result && (
                <p role="alert" className="mt-3 text-xs leading-relaxed text-rose-800">
                  {error}
                </p>
              )}

              {/* Action Buttons */}
              <div className="mt-auto grid grid-cols-1 gap-2 pt-4">
                <button
                  type="button"
                  onClick={() => void generate()}
                  disabled={isGenerating}
                  aria-label="Tạo lại ảnh minh họa"
                  className="rounded-full bg-[#1A1918] px-4 py-2.5 text-xs font-semibold text-[#FBFBF9] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#302B27] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-55 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9C5234]"
                >
                  {isGenerating ? 'Đang tạo...' : 'Mặc thử lại'}
                </button>

                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => void toggleBookmark()}
                    disabled={isSaving}
                    aria-label={saved ? 'Bỏ lưu bộ đồ' : 'Lưu bộ đồ'}
                    aria-pressed={saved}
                    className="rounded-full bg-[#EEEAE2] px-3 py-2 text-xs font-semibold text-[#1A1918] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#E2DDD3] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-55 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9C5234]"
                  >
                    {isSaving ? '...' : saved ? '✓ Đã lưu' : 'Lưu bộ đồ'}
                  </button>

                  <button
                    type="button"
                    onClick={() => void handleRecordWorn()}
                    disabled={isRecordingWorn || worn}
                    className={`rounded-full px-3 py-2 text-xs font-semibold transition duration-300 active:scale-[0.98] disabled:cursor-not-allowed ${
                      worn
                        ? 'bg-[#E3EFE3] text-[#2D5A27]'
                        : 'bg-[#EEEAE2] text-[#1A1918] hover:bg-[#E2DDD3]'
                    }`}
                  >
                    {isRecordingWorn ? '...' : worn ? '✓ Mặc hôm nay' : 'Mặc hôm nay'}
                  </button>
                </div>
              </div>
            </aside>
          </div>
        </div>
      </section>
    </div>
  );
}
