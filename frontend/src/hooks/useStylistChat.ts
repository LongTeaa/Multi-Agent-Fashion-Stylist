'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { sendStylistChat, ApiError } from '@/lib/api';
import type { StylistChatResponseData } from '@/types/chat';

export type ChatStatus = 'idle' | 'loading' | 'success' | 'clarification' | 'error';

export interface UseStylistChatState {
  status: ChatStatus;
  response: StylistChatResponseData | null;
  error: ApiError | null;
  lastQuery: string;
  lastLocation?: string;
  isLoading: boolean;
}

export interface UseStylistChatReturn extends UseStylistChatState {
  sendMessage: (query: string, location?: string) => Promise<void>;
  retry: () => Promise<void>;
  reset: () => void;
  clearError: () => void;
}

export function useStylistChat(): UseStylistChatReturn {
  const [status, setStatus] = useState<ChatStatus>('idle');
  const [response, setResponse] = useState<StylistChatResponseData | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [lastQuery, setLastQuery] = useState<string>('');
  const [lastLocation, setLastLocation] = useState<string | undefined>(undefined);

  // Request sequence counter to discard stale out-of-order responses (race condition prevention)
  const sequenceIdRef = useRef<number>(0);
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID());
  const isMountedRef = useRef<boolean>(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const sendMessage = useCallback(async (query: string, location?: string, retryKey?: string) => {
    const trimmedQuery = query.trim();
    if (!trimmedQuery || trimmedQuery.length > 1000) return;

    const trimmedLocation = location?.trim().slice(0, 200) || undefined;
    const currentSequenceId = ++sequenceIdRef.current;
    const currentIdempotencyKey = retryKey || crypto.randomUUID();
    idempotencyKeyRef.current = currentIdempotencyKey;

    setLastQuery(trimmedQuery);
    setLastLocation(trimmedLocation);
    setStatus('loading');
    setError(null);
    // Suppress previous response while new recommendation is being generated
    setResponse(null);

    try {
      const data = await sendStylistChat({
        query: trimmedQuery,
        location: trimmedLocation || null,
        idempotency_key: currentIdempotencyKey,
      });

      // Ignore if unmounted or if a newer request was dispatched while this one was in flight
      if (!isMountedRef.current || sequenceIdRef.current !== currentSequenceId) {
        return;
      }

      setResponse(data);
      if (data.needs_clarification) {
        setStatus('clarification');
      } else {
        setStatus('success');
      }
    } catch (err) {
      if (!isMountedRef.current || sequenceIdRef.current !== currentSequenceId) {
        return;
      }

      const apiErr =
        err instanceof ApiError
          ? err
          : new ApiError(
              (err as Error)?.message || 'Có lỗi không xác định xảy ra.',
              'UNKNOWN_ERROR',
              500,
              err
            );
      setError(apiErr);
      setStatus('error');
    }
  }, []);

  const retry = useCallback(async () => {
    if (!lastQuery) return;
    await sendMessage(lastQuery, lastLocation, idempotencyKeyRef.current);
  }, [lastQuery, lastLocation, sendMessage]);

  const reset = useCallback(() => {
    sequenceIdRef.current++;
    setStatus('idle');
    setResponse(null);
    setError(null);
    setLastQuery('');
    setLastLocation(undefined);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
    if (status === 'error') {
      setStatus('idle');
    }
  }, [status]);

  return {
    status,
    response,
    error,
    lastQuery,
    lastLocation,
    isLoading: status === 'loading',
    sendMessage,
    retry,
    reset,
    clearError,
  };
}
