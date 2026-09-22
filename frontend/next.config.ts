import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // LT-09: Allow specific dev origin used during testing (e.g. host-only network IP)
  // Scoped strictly without arbitrary wildcards.
  allowedDevOrigins: ['192.168.56.1'],
};

export default nextConfig;
