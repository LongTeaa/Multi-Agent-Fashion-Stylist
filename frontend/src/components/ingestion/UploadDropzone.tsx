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
    <div className="w-full max-w-4xl mx-auto p-6 bg-white/80 backdrop-blur-md rounded-2xl shadow-xl border border-slate-200/80 transition-all">
      <div className="text-center mb-6">
        <h2 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Tải Lên & Số Hóa Quần Áo
        </h2>
        <p className="mt-2 text-sm text-slate-600">
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
        className={`relative flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-xl cursor-pointer transition-all duration-200 ${
          isDragOver
            ? 'border-indigo-500 bg-indigo-50/50 scale-[1.01]'
            : 'border-slate-300 hover:border-indigo-400 bg-slate-50/60 hover:bg-slate-50'
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

        <div className="w-14 h-14 mb-4 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 shadow-inner">
          <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
        </div>

        <p className="text-base font-semibold text-slate-700">
          Kéo thả ảnh vào đây hoặc <span className="text-indigo-600 underline">chọn tệp từ máy</span>
        </p>
        <p className="text-xs text-slate-500 mt-1">
          Định dạng hỗ trợ: JPEG, PNG, WebP • Tối đa 10 ảnh • Kích thước tối đa 10 MB/ảnh
        </p>
      </div>

      {/* Option Declared Kind */}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-4 p-4 bg-slate-50 rounded-xl border border-slate-200/70">
        <label htmlFor="input-kind-select" className="text-sm font-medium text-slate-700">
          Gợi ý ngữ cảnh ảnh (Tùy chọn):
        </label>
        <select
          id="input-kind-select"
          value={declaredKind}
          onChange={(e) => setDeclaredKind(e.target.value)}
          className="px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">Tự động nhận diện (Khuyến nghị)</option>
          <option value="single_item">Một món đồ riêng lẻ (Áo/Quần chụp phẳng)</option>
          <option value="multi_item">Nhiều món xếp chung</option>
          <option value="worn_outfit">Trang phục đang mặc trên người (OOTD)</option>
        </select>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mt-4 p-3 bg-rose-50 border border-rose-200 text-rose-700 rounded-lg text-sm flex items-center gap-2">
          <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      {/* Preview Grid */}
      {selectedFiles.length > 0 && (
        <div className="mt-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-800">
              Đã chọn ({selectedFiles.length}/{MAX_FILES} ảnh)
            </h3>
            <button
              type="button"
              onClick={() => {
                previews.forEach((url) => URL.revokeObjectURL(url));
                setSelectedFiles([]);
                setPreviews([]);
              }}
              className="text-xs text-slate-500 hover:text-rose-600 transition"
            >
              Xóa tất cả
            </button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-5 gap-3">
            {selectedFiles.map((file, idx) => (
              <div
                key={idx}
                className="relative group rounded-lg overflow-hidden border border-slate-200 bg-white shadow-sm aspect-square"
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
                    className="p-1.5 bg-rose-600 text-white rounded-full hover:bg-rose-700 transition"
                    title="Xóa ảnh này"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
                <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent p-1.5 text-[11px] text-white truncate">
                  {file.name}
                </div>
              </div>
            ))}
          </div>

          {/* Action Button */}
          <div className="mt-6 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={handleStartUpload}
              disabled={isUploading}
              className={`px-6 py-2.5 rounded-xl font-medium text-white shadow-lg transition-all flex items-center gap-2 ${
                isUploading
                  ? 'bg-indigo-400 cursor-not-allowed'
                  : 'bg-indigo-600 hover:bg-indigo-700 active:scale-95 shadow-indigo-200'
              }`}
            >
              {isUploading ? (
                <>
                  <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Đang tải lên và phân tích...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                  Tiến hành phân tích ({selectedFiles.length} ảnh)
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
