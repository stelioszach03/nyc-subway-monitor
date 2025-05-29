/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  
  // Disable SWC minifier if causing hydration issues
  swcMinify: false,
  
  // Environment variables
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000',
    NEXT_PUBLIC_MAPBOX_TOKEN: process.env.NEXT_PUBLIC_MAPBOX_TOKEN || '',
  },
  
  // Disable font optimization if causing hydration issues
  optimizeFonts: false,
  
  // Optimize for production
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production' ? {
      exclude: ['error', 'warn']
    } : false,
  },
  
  // Image optimization
  images: {
    domains: ['api.mapbox.com'],
    unoptimized: true, // Disable image optimization if causing issues
  },
  
  // Experimental features
  experimental: {
    optimizePackageImports: ['@visx/visx', 'd3'],
  },
  
  // Add webpack config for better error handling
  webpack: (config, { isServer }) => {
    // Ignore certain warnings
    config.ignoreWarnings = [
      { module: /node_modules\/mapbox-gl/ },
    ]
    
    if (!isServer) {
      // Don't resolve fs module on client side
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
      }
    }
    
    return config
  },
}

export default nextConfig