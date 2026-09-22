'use client';

import { useEffect, useState, type ImgHTMLAttributes } from 'react';
import { getMediaUrl, getStoredUserId } from '@/lib/api';

export type PrivateMediaImageProps = Omit<ImgHTMLAttributes<HTMLImageElement>, 'src'> & {
  source: string;
  fallbackText?: string;
  showRetryButton?: boolean;
};

/** Load private media with the same identity header used by JSON requests. */
export function PrivateMediaImage({
  source,
  alt,
  fallbackText = 'Không thể tải ảnh',
  showRetryButton = true,
  ...imageProps
}: PrivateMediaImageProps) {
  const [loaded, setLoaded] = useState<{ source: string; url: string } | null>(null);
  const [failedSource, setFailedSource] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  const isPrivate = Boolean(source && source.startsWith('/api/v1/media/'));
  const hasError = isPrivate ? failedSource === source : failedSource === source;
  const resolvedUrl = isPrivate
    ? (loaded?.source === source ? loaded.url : null)
    : getMediaUrl(source);

  useEffect(() => {
    if (!isPrivate) return;
    let objectUrl: string | null = null;
    let active = true;
    const controller = new AbortController();

    void fetch(getMediaUrl(source), {
      headers: { 'X-User-Id': getStoredUserId() },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`Media request failed: ${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (active) {
          setLoaded({ source, url: objectUrl });
          setFailedSource(null);
        } else {
          URL.revokeObjectURL(objectUrl);
        }
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        if (active) {
          setLoaded(null);
          setFailedSource(source);
        }
      });

    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [source, isPrivate, retryKey]);

  if (hasError) {
    return (
      <div
        data-testid="private-media-error"
        className={`flex flex-col items-center justify-center p-3 text-center bg-[#242220] rounded-xl text-[#A8A29E] border border-[#3D3A37] min-h-[120px] ${
          imageProps.className || ''
        }`}
      >
        <svg className="w-8 h-8 mb-1.5 text-amber-500/80" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <span className="text-xs font-mono text-[#D6D1C7] mb-1">{fallbackText}</span>
        {showRetryButton && (
          <button
            type="button"
            onClick={() => {
              setFailedSource(null);
              setRetryKey((k) => k + 1);
            }}
            className="mt-1 px-3 py-1 text-xs font-medium rounded-lg bg-[#3D3A37] hover:bg-[#4E4A46] text-white border border-[#524E49] transition shadow-xs cursor-pointer"
          >
            Thử tải lại ảnh
          </button>
        )}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      {...imageProps}
      src={resolvedUrl ?? undefined}
      alt={alt}
      onError={(e) => {
        if (!isPrivate) {
          setFailedSource(source);
        }
        imageProps.onError?.(e);
      }}
    />
  );
}
