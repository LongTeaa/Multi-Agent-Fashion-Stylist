/**
 * RFC 4122 version 4 UUID that works outside a secure context.
 *
 * `crypto.randomUUID` exists only on HTTPS and localhost, so a demo opened at
 * `http://<lan-ip>:3000` would throw. `crypto.getRandomValues` is available in
 * every context and is used to build the UUID there; `Math.random` is a last
 * resort for runtimes without Web Crypto. Every result passes the backend's
 * UUID v4 validation.
 */
export function generateUUIDv4(): string {
  const webCrypto: Crypto | undefined = typeof crypto !== 'undefined' ? crypto : undefined;

  if (typeof webCrypto?.randomUUID === 'function') {
    return webCrypto.randomUUID();
  }

  const bytes = new Uint8Array(16);
  if (typeof webCrypto?.getRandomValues === 'function') {
    webCrypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }

  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // RFC 4122 variant

  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
