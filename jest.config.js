module.exports = {
  testEnvironment: 'jsdom',
  roots: ['<rootDir>/static/js/dev'],
  testMatch: ['**/__tests__/**/*.test.js'],
  transform: {
    '^.+\\.js$': 'babel-jest',
  },
  setupFilesAfterEnv: ['<rootDir>/static/js/dev/__tests__/setup.js'],
  moduleNameMapper: {
    '^sortablejs$': '<rootDir>/node_modules/sortablejs/Sortable.min.js',
  },
  collectCoverageFrom: [
    'static/js/dev/**/*.js',
    '!static/js/dev/__tests__/**',
  ],
  coverageThreshold: {
    global: {
      branches: 30,
      functions: 40,
      lines: 40,
      statements: 40,
    },
  },
};
