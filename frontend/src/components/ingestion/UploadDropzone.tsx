'use client';

import React, { useState, useRef, useCallback } from 'react';

interface UploadDropzoneProps {
  onUpload: (files: File[], declaredKind?: string) => Promise<void>;
  isUploading: boolean;
}

const MAX_FILES = 10;
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

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
    <div className="double-bezel-shell max-w-4xl mx-auto">
      <div className="double-bezel-core p-6 sm:p-10 border border-[#E8E5DE]">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#E8E5DE] bg-[#FAF8F5] text-[#736E65] text-[10px] font-mono tracking-[0.2em] uppercase mb-4">
            <span className="w-1.5 h-1.5 rounded-full bg-[#9C5234]" />
            <span>AI Vision Ingestion</span>
          </div>
          <h2 className="font-serif text-3xl sm:text-4xl font-normal tracking-tight text-[#1A1918]">
            Tải Lên & Số Hóa Quần Áo
          </h2>
          <p className="mt-3 text-sm sm:text-base text-[#5C564E] max-w-xl mx-auto leading-relaxed">
            Chụp ảnh món đồ riêng lẻ hoặc trang phục bạn đang mặc. AI sẽ tự động tách từng món và phân tích thuộc tính phong cách.
          </p>
        </div>

        {/* Drag and Drop Box */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragOver(true);
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`relative flex flex-col items-center justify-center p-8 sm:p-12 border-2 border-dashed rounded-2xl cursor-pointer transition-all duration-300 ${
            isDragOver
              ? 'border-[#9C5234] bg-[#9C5234]/5 scale-[1.01]'
              : 'border-[#D5D1C7] hover:border-[#9C5234] bg-[#FAF8F5]/80 hover:bg-[#F5F2EC]/80'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={(e) => {
              if (e.target.files) handleFiles(e.target.files);
            }}
          />

          <div className="w-16 h-16 mb-4 rounded-full bg-[#9C5234]/10 text-[#9C5234] flex items-center justify-center shadow-2xs">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>

          <p className="text-sm sm:text-base font-medium text-[#1A1918]">
            Kéo thả ảnh vào đây hoặc <span className="text-[#9C5234] underline font-semibold hover:text-[#7A3F27]">chọn tệp từ máy</span>
          </p>
          <p className="text-xs font-mono text-[#736E65] mt-1.5">
            Định dạng hỗ trợ: JPEG, PNG, WebP • Tối đa 10 ảnh • Kích thước tối đa 10 MB/ảnh
          </p>
        </div>

        {/* Option Declared Kind */}
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 p-4 bg-[#FAF8F5] rounded-2xl border border-[#E8E5DE]">
          <label htmlFor="input-kind-select" className="text-xs font-mono uppercase tracking-wider text-[#5C564E] font-medium">
            Gợi ý ngữ cảnh ảnh (Tùy chọn):
          </label>
          <select
            id="input-kind-select"
            value={declaredKind}
            onChange={(e) => setDeclaredKind(e.target.value)}
            className="px-3.5 py-2 text-xs font-mono bg-white border border-[#D5D1C7] rounded-xl text-[#1A1918] focus:border-[#9C5234] focus:ring-1 focus:ring-[#9C5234] outline-none shadow-2xs"
          >
            <option value="">Tự động nhận diện (Khuyến nghị)</option>
            <option value="single_item">Một món đồ riêng lẻ (Áo/Quần chụp phẳng)</option>
            <option value="multi_item">Nhiều món xếp chung</option>
            <option value="worn_outfit">Trang phục đang mặc trên người (OOTD)</option>
          </select>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mt-4 p-3.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs sm:text-sm flex items-center gap-2">
            <svg className="w-5 h-5 flex-shrink-0 text-rose-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* Preview Grid */}
        {selectedFiles.length > 0 && (
          <div className="mt-6 pt-6 border-t border-[#E8E5DE]">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-mono uppercase tracking-wider text-[#1A1918] font-semibold">
                Đã chọn ({selectedFiles.length}/{MAX_FILES} ảnh)
              </h3>
              <button
                type="button"
                onClick={() => {
                  previews.forEach((url) => URL.revokeObjectURL(url));
                  setSelectedFiles([]);
                  setPreviews([]);
                }}
                className="text-xs font-mono text-[#736E65] hover:text-rose-600 transition"
              >
                Xóa tất cả
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-5 gap-3">
              {selectedFiles.map((file, idx) => (
                <div
                  key={idx}
                  className="relative group rounded-xl overflow-hidden border border-[#E8E5DE] bg-white shadow-2xs aspect-square"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={previews[idx]}
                    alt={file.name}
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRemoveFile(idx);
                      }}
                      className="p-1.5 bg-[#1A1918]/90 text-white rounded-full hover:bg-rose-600 transition"
                      title="Xóa ảnh này"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                  <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent p-1.5 text-[10px] font-mono text-white truncate">
                    {file.name}
                  </div>
                </div>
              ))}
            </div>

            {/* Action Button */}
            <div className="mt-6 flex items-center justify-end">
              <button
                type="button"
                onClick={handleStartUpload}
                disabled={isUploading}
                className={`tactile-btn group inline-flex items-center gap-3 pl-6 pr-2 py-2.5 rounded-full text-xs font-mono uppercase tracking-wider text-white shadow-sm transition-all ${
                  isUploading
                    ? 'bg-[#736E65] cursor-not-allowed opacity-70'
                    : 'bg-[#1A1918] hover:bg-[#2D2420]'
                }`}
              >
                {isUploading ? (
                  <>
                    <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <span>Đang tải lên và phân tích...</span>
                  </>
                ) : (
                  <>
                    <span>Tiến hành phân tích ({selectedFiles.length} ảnh)</span>
                    <span className="w-6 h-6 rounded-full bg-white/15 flex items-center justify-center group-hover:translate-x-0.5 transition-all text-xs">
                      →
                    </span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
