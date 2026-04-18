import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",

  env: {
    WALLET_API_URL: process.env.WALLET_API_URL ?? "",
    STOCK_API_URL:  process.env.STOCK_API_URL  ?? "",
    SESSION_AUTH_URL: process.env.SESSION_AUTH_URL ?? "",
    UI_API_URL: process.env.UI_API_URL ?? "",
  },

  experimental: {
    serverActions: {
      allowedOrigins: [
        "next.localhost",
        "next.localhost:8081",
      ],
    },
  },
};

export default nextConfig;
