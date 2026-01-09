/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./templates/DataProcessor/**/*.html",
    "./templates/DocumentProcessor/**/*.html",
    "./templates/WebScraper/**/*.html",
    "./templates/KeywordSelection/**/*.html",
    "./templates/Pages/**/*.html",
    "./static/js/**/*.js",
  ],
  safelist: [
    // Toast notification classes (applied dynamically via JS)
    'toast',
    'toast-success',
    'toast-warning',
    'toast-error',
    'toast-info',
    // Skeleton loader classes
    'skeleton',
    'skeleton-text',
    'skeleton-heading',
    'skeleton-card',
    // Loading states
    'spinner',
    'spinner-sm',
    'spinner-lg',
    // Animation classes that may be applied dynamically
    'animate-pulse',
    'animate-fade-in',
    'animate-fade-in-up',
    'animate-scale-in',
    'animate-slide-in-right',
    // Transform classes for toast animations
    'translate-x-full',
    'translate-x-0',
    // Step dot colors for progress indicator
    'bg-success-500',
    'bg-primary-500',
    'bg-charcoal-200',
    'bg-danger-100',
  ],
  theme: {
    extend: {
      colors: {
        // Primary palette - Deep Teal (Florida coastal vibes)
        primary: {
          50: '#E6F4F4',
          100: '#CCE9E9',
          200: '#99D3D4',
          300: '#66BDBF',
          400: '#33A7AA',
          500: '#0D7377', // Main primary
          600: '#0A5C5F',
          700: '#084547',
          800: '#052E2F',
          900: '#031718',
        },
        // Secondary palette - Warm Coral (sunset accents)
        coral: {
          50: '#FFF0F0',
          100: '#FFE1E1',
          200: '#FFC3C3',
          300: '#FFA5A5',
          400: '#FF8787',
          500: '#FF6B6B', // Main coral
          600: '#CC5656',
          700: '#994040',
          800: '#662B2B',
          900: '#331515',
        },
        // Neutral palette - Charcoal tones
        charcoal: {
          50: '#F8F9FA',  // Warm Gray (background)
          100: '#E9ECEF',
          200: '#DEE2E6',
          300: '#CED4DA',
          400: '#ADB5BD',
          500: '#6C757D',
          600: '#495057',
          700: '#343A40',
          800: '#2D3436', // Main charcoal
          900: '#1A1D1E',
        },
        // Semantic colors
        success: {
          50: '#ECFDF5',
          100: '#D1FAE5',
          200: '#A7F3D0',
          300: '#6EE7B7',
          400: '#34D399',
          500: '#10B981', // Emerald
          600: '#059669',
          700: '#047857',
          800: '#065F46',
          900: '#064E3B',
        },
        warning: {
          50: '#FFFBEB',
          100: '#FEF3C7',
          200: '#FDE68A',
          300: '#FCD34D',
          400: '#FBBF24',
          500: '#F59E0B', // Amber
          600: '#D97706',
          700: '#B45309',
          800: '#92400E',
          900: '#78350F',
        },
        danger: {
          50: '#FEF2F2',
          100: '#FEE2E2',
          200: '#FECACA',
          300: '#FCA5A5',
          400: '#F87171',
          500: '#EF4444',
          600: '#DC2626',
          700: '#B91C1C',
          800: '#991B1B',
          900: '#7F1D1D',
        },
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        body: ['system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Monaco', 'monospace'],
      },
      fontSize: {
        'display-2xl': ['4.5rem', { lineHeight: '1', letterSpacing: '-0.02em', fontWeight: '700' }],
        'display-xl': ['3.75rem', { lineHeight: '1.1', letterSpacing: '-0.02em', fontWeight: '700' }],
        'display-lg': ['3rem', { lineHeight: '1.1', letterSpacing: '-0.01em', fontWeight: '600' }],
        'display-md': ['2.25rem', { lineHeight: '1.2', letterSpacing: '-0.01em', fontWeight: '600' }],
        'display-sm': ['1.875rem', { lineHeight: '1.25', letterSpacing: '0', fontWeight: '600' }],
        'display-xs': ['1.5rem', { lineHeight: '1.3', letterSpacing: '0', fontWeight: '600' }],
      },
      boxShadow: {
        'soft-sm': '0 2px 8px -2px rgba(45, 52, 54, 0.08)',
        'soft': '0 4px 16px -4px rgba(45, 52, 54, 0.12)',
        'soft-md': '0 8px 24px -6px rgba(45, 52, 54, 0.15)',
        'soft-lg': '0 12px 32px -8px rgba(45, 52, 54, 0.18)',
        'soft-xl': '0 20px 48px -12px rgba(45, 52, 54, 0.22)',
        'glow-primary': '0 0 24px -4px rgba(13, 115, 119, 0.35)',
        'glow-coral': '0 0 24px -4px rgba(255, 107, 107, 0.35)',
        'inner-soft': 'inset 0 2px 6px -2px rgba(45, 52, 54, 0.06)',
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
        '4xl': '2rem',
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
        '30': '7.5rem',
      },
      transitionDuration: {
        '250': '250ms',
        '350': '350ms',
      },
      transitionTimingFunction: {
        'bounce-in': 'cubic-bezier(0.68, -0.55, 0.265, 1.55)',
        'smooth': 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out forwards',
        'fade-in-up': 'fadeInUp 0.6s ease-out forwards',
        'fade-in-down': 'fadeInDown 0.6s ease-out forwards',
        'scale-in': 'scaleIn 0.3s ease-out forwards',
        'slide-in-right': 'slideInRight 0.4s ease-out forwards',
        'slide-in-left': 'slideInLeft 0.4s ease-out forwards',
        'pulse-soft': 'pulseSoft 2s ease-in-out infinite',
        'shimmer': 'shimmer 2s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeInDown: {
          '0%': { opacity: '0', transform: 'translateY(-16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(24px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        slideInLeft: {
          '0%': { opacity: '0', transform: 'translateX(-24px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(var(--tw-gradient-stops))',
        'shimmer': 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.4) 50%, transparent 100%)',
      },
    },
  },
  plugins: [],
};
