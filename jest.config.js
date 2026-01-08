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
};
