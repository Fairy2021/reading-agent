/** @type {import('next').NextConfig} */
const backendOrigin = process.env.INTERNAL_API_BASE_URL || "http://api:8000";

const nextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
