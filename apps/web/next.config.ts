import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["plotly.js-dist-min"],
};

export default nextConfig;
