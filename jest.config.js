module.exports = {
  testEnvironment: 'jsdom',
  roots: ['<rootDir>/static/js/dev'],
  testMatch: ['**/__tests__/**/*.test.js'],
  transform: {
    '^.+\\.js$': 'babel-jest',
  },
  setupFilesAfterEnv: ['<rootDir>/static/js/dev/__tests__/setup.js'],
  collectCoverageFrom: [
    'static/js/dev/**/*.js',
    '!static/js/dev/__tests__/**',
    // mobile.js is DOM-heavy progressive enhancement (mobile nav/menus) that
    // isn't unit-tested; exclude it so the gate measures the logic we do test.
    '!static/js/dev/mobile.js',
  ],
  coverageThreshold: {
    // Meaningful floor over the tested surface (common.js + the chart adapter).
    global: {
      branches: 55,
      functions: 55,
      lines: 65,
      statements: 65,
    },
    // Gate the dashboard chart adapter (the JS worth locking down) harder.
    './static/js/dev/marketInsights.js': {
      branches: 70,
      functions: 65,
      lines: 85,
      statements: 85,
    },
  },
};
