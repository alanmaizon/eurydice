/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // Allow images from any hostname for inline image messages
  images: {
    remotePatterns: [],
  },
}

module.exports = nextConfig
