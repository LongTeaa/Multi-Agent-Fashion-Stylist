import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Set a comma-separated list of hostnames when accessing the dev server
  // through a local network interface.
  allowedDevOrigins: process.env.NEXT_ALLOWED_DEV_ORIGINS
    ?.split(',')
    .map((origin) => origin.trim())
    .filter(Boolean),
};

export default nextConfig;
