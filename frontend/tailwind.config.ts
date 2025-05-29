import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        subway: {
          '1': '#EE352E',
          '2': '#EE352E',
          '3': '#EE352E',
          '4': '#00933C',
          '5': '#00933C',
          '6': '#00933C',
          '7': '#B933AD',
          'A': '#0039A6',
          'C': '#0039A6',
          'E': '#0039A6',
          'B': '#FF6319',
          'D': '#FF6319',
          'F': '#FF6319',
          'M': '#FF6319',
          'G': '#6CBE45',
          'J': '#996633',
          'Z': '#996633',
          'L': '#A7A9AC',
          'N': '#FCCC0A',
          'Q': '#FCCC0A',
          'R': '#FCCC0A',
          'W': '#FCCC0A',
          'S': '#808183',
        },
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'slide-in': 'slideIn 0.3s ease-out',
        'fade-in': 'fadeIn 0.5s ease-out',
      },
      keyframes: {
        slideIn: {
          '0%': { transform: 'translateX(100%)' },
          '100%': { transform: 'translateX(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}

export default config