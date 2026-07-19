/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  webpack(config, { dev }) {
    if (dev) {
      // Stabilize local Windows dev by avoiding persistent webpack pack cache corruption/ENOENT.
      config.cache = false;
    }
    return config;
  },
  async headers() {
    return [
      {
        source: "/fonts/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=31536000, immutable"
          }
        ]
      }
    ];
  },
  async redirects() {
    return [
      {
        source: "/source-videos/:id/transcript-editor",
        destination: "/production/transcript-editor/:id",
        permanent: false
      },
      {
        source: "/source-videos/:id/final-review",
        destination: "/production/final-review/:id",
        permanent: false
      }
    ];
  },
  async rewrites() {
    const apiUpstreamUrl = process.env.API_UPSTREAM_URL ?? "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUpstreamUrl}/:path*`
      }
    ];
  }
};

export default nextConfig;
