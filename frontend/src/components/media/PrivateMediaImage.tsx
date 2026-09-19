'use client';

import { useEffect, useState, type ImgHTMLAttributes } from 'react';
import { getMediaUrl, getStoredUserId } from '@/lib/api';

type PrivateMediaImageProps = Omit<ImgHTMLAttributes<HTMLImageElement>, 'src'> & {
  source: string;
};

/** Load private media with the same identity header used by JSON requests. */
export function PrivateMediaImage({ source, alt, ...imageProps }: PrivateMediaImageProps) {
  const [loaded, setLoaded] = useState<{ source: string; url: string } | null>(null);
  const isPrivate = source.startsWith('/api/v1/media/');
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
        if (active) setLoaded({ source, url: objectUrl });
        else URL.revokeObjectURL(objectUrl);
      })
      .catch(() => {
        if (active) setLoaded(null);
      });

    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [source, isPrivate]);

  // eslint-disable-next-line @next/next/no-img-element
  return <img {...imageProps} src={resolvedUrl ?? undefined} alt={alt} />;
}
