import { afterEach, describe, expect, it, vi } from 'vitest';
import { generateUUIDv4 } from '@/lib/uuid';
import { getStoredSessionId, getStoredUserId } from '@/lib/api';

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('generateUUIDv4', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
    sessionStorage.clear();
  });

  it('uses crypto.randomUUID when it is available', () => {
    const native = vi.spyOn(crypto, 'randomUUID');
    expect(generateUUIDv4()).toMatch(UUID_V4);
    expect(native).toHaveBeenCalledTimes(1);
  });

  it('builds the UUID from crypto.getRandomValues outside a secure context', () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (bytes: Uint8Array) => bytes.fill(0xff),
    });
    expect(generateUUIDv4()).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff');
  });

  it('falls back to Math.random when Web Crypto is missing', () => {
    vi.stubGlobal('crypto', undefined);
    const random = vi.spyOn(Math, 'random').mockReturnValue(0);
    expect(generateUUIDv4()).toBe('00000000-0000-4000-8000-000000000000');
    expect(random).toHaveBeenCalled();
  });

  it('produces distinct identifiers', () => {
    const ids = new Set(Array.from({ length: 50 }, () => generateUUIDv4()));
    expect(ids.size).toBe(50);
  });

  // Browsers expose crypto.randomUUID only in a secure context (HTTPS or localhost).
  it('lets the demo user and session identifiers load over plain http on a LAN address', () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (bytes: Uint8Array) => {
        for (let index = 0; index < bytes.length; index += 1) bytes[index] = index * 17;
        return bytes;
      },
    });
    expect(typeof (crypto as Partial<Crypto>).randomUUID).toBe('undefined');

    expect(getStoredUserId()).toMatch(UUID_V4);
    expect(getStoredSessionId()).toMatch(UUID_V4);
  });
});
