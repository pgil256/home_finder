// Jest test setup file

// Mock window.alert
window.alert = jest.fn();

// Mock console methods to reduce noise
const originalConsole = global.console;
global.console = {
  ...originalConsole,
  log: jest.fn(),
  error: jest.fn(),
};

// Reset mocks between tests
beforeEach(() => {
  // Set up fresh fetch mock for each test
  global.fetch = jest.fn();
  window.alert.mockClear();
  document.body.innerHTML = '';
});
