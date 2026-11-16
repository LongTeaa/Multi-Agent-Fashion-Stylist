'use client';

import React, { useState, useRef, useCallback } from 'react';
import { AlertIcon, ArrowRightIcon, CameraIcon, CloseIcon, Spinner } from '@/components/ui/icons';

interface UploadDropzoneProps {
  onUpload: (files: File[], declaredKind?: string) => Promise<void>;
  isUploading: boolean;
}

const MAX_FILES = 10;
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

const KIND_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Tự nhận diện' },
  { value: 'single_item', label: 'Một món' },
  { value: 'multi_item', label: 'Nhiều món' },
  { value: 'worn_outfit', label: 'Bộ đang mặc' },
];

export function UploadDropzone({ onUpload, isUploading }: UploadDropzoneProps) {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [declaredKind, setDeclaredKind] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback((files: FileList | File[]) => {
    setError(null);
    const newFiles: File[] = [];
    const newPreviews: string[] = [];

    const fileArray = Array.from(files);
    if (selectedFiles.length + fileArray.length > MAX_FILES) {
      setError(`Bạn chỉ có thể tải lên tối đa ${MAX_FILES} ảnh cùng một lúc.`);
      return;
    }

    for (const file of fileArray) {
      if (!ALLOWED_TYPES.includes(file.type)) {
        setError(`Định dạng tệp "${file.name}" không được hỗ trợ. Vui lòng chọn ảnh JPEG, PNG hoặc WebP.`);
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setError(`Tệp "${file.name}" vượt quá kích thước tối đa cho phép (10 MB).`);
        return;
      }
      newFiles.push(file);
      newPreviews.push(URL.createObjectURL(file));
    }

    setSelectedFiles((prev) => [...prev, ...newFiles]);
    setPreviews((prev) => [...prev, ...newPreviews]);
  }, [selectedFiles.length]);

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const handleRemoveFile = (index: number) => {
    URL.revokeObjectURL(previews[index]);
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    setPreviews((prev) => prev.filter((_, i) => i !== index));
  };

  const handleStartUpload = async () => {
    if (selectedFiles.length === 0) {
      setError('Vui lòng chọn ít nhất 1 ảnh để tải lên.');
      return;
    }
    setError(null);
    try {
      await onUpload(selectedFiles, declaredKind || undefined);
    } catch (err: unknown) {
      setError((err as Error).message || 'Tải ảnh lên thất bại. Vui lòng thử lại.');
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 text-center">
        <h2 className="display text-[2rem] sm:text-[2.5rem]">Thêm món đồ</h2>
        <p className="mx-auto mt-2 max-w-lg text-[0.9375rem] leading-relaxed text-ink-2">
          Chụp từng món, nhiều món xếp chung hoặc cả bộ bạn đang mặc. Mỗi món sẽ được tách riêng để bạn kiểm tra trước
          khi lưu.
        </p>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed px-6 py-12 text-center transition-colors sm:py-16 ${
          isDragOver ? 'border-accent bg-accent-soft' : 'border-line-strong bg-surface hover:border-ink'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          aria-label="Chọn ảnh trang phục để tải lên"
          multiple
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) handleFiles(e.target.files);
            e.target.value = '';
          }}
        />
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-sunken text-ink">
          <CameraIcon size={26} />
        </span>
        <p className="mt-4 text-[1rem] font-semibold text-ink">
          Kéo thả ảnh vào đây hoặc <span className="text-accent underline underline-offset-4">chọn ảnh</span>
        </p>
        <p className="mt-1.5 text-sm text-muted">JPEG, PNG, WebP · tối đa 10 ảnh, mỗi ảnh 10 MB</p>
      </div>

      {/* Optional hint about what the photos show */}
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <span className="mr-1 text-sm text-muted" id="input-kind-label">
          Loại ảnh:
        </span>
        <div role="group" aria-labelledby="input-kind-label" className="flex flex-wrap gap-2">
          {KIND_OPTIONS.map((option) => (
            <button
              key={option.value || 'auto'}
              type="button"
              aria-pressed={declaredKind === option.value}
              onClick={() => setDeclaredKind(option.value)}
              className="chip"
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div role="alert" className="notice notice-danger mt-5">
          <AlertIcon size={18} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {selectedFiles.length > 0 && (
        <div className="mt-8 border-t border-line pt-6">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">
              Đã chọn {selectedFiles.length}/{MAX_FILES} ảnh
            </h3>
            <button
              type="button"
              onClick={() => {
                previews.forEach((url) => URL.revokeObjectURL(url));
                setSelectedFiles([]);
                setPreviews([]);
              }}
              className="btn btn-ghost btn-sm"
            >
              Bỏ chọn tất cả
            </button>
          </div>

          <ul className="grid grid-cols-3 gap-3 sm:grid-cols-5">
            {selectedFiles.map((file, idx) => (
              <li key={idx} className="relative aspect-square overflow-hidden rounded-xl bg-sunken">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={previews[idx]} alt={file.name} className="h-full w-full object-cover" />
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRemoveFile(idx);
                  }}
                  className="absolute right-1.5 top-1.5 flex h-7 w-7 items-center justify-center rounded-full bg-ink/80 text-paper hover:bg-danger"
                  aria-label={`Bỏ ảnh ${file.name}`}
                >
                  <CloseIcon size={14} />
                </button>
              </li>
            ))}
          </ul>

          <div className="mt-6 flex justify-end">
            <button type="button" onClick={handleStartUpload} disabled={isUploading} className="btn btn-primary btn-lg">
              {isUploading ? (
                <>
                  <Spinner size={16} />
                  Đang tải ảnh lên…
                </>
              ) : (
                <>
                  Nhận diện {selectedFiles.length} ảnh
                  <ArrowRightIcon size={16} />
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
