/**
 * Tests for common.js utilities
 * innerHTML usage here is test-only with hardcoded fixtures, not user input.
 */

const {
  ToastManager,
  SkeletonLoader,
  LoadingButton,
  smoothScrollTo,
  debounce,
} = require('../common.js');

describe('ToastManager', () => {
  let toastManager;

  beforeEach(() => {
    document.body.innerHTML = '';
    toastManager = new ToastManager();
  });

  test('creates toast container on init', () => {
    const container = document.getElementById('toast-container');
    expect(container).not.toBeNull();
    expect(container.getAttribute('aria-live')).toBe('polite');
    expect(container.getAttribute('aria-atomic')).toBe('true');
  });

  test('reuses existing toast container', () => {
    // toastManager already created one in beforeEach; creating another should reuse it
    const existingContainer = document.getElementById('toast-container');
    const tm = new ToastManager();
    const containers = document.querySelectorAll('#toast-container');
    expect(containers.length).toBe(1);
    expect(tm.container).toBe(existingContainer);
  });

  test('show() creates a toast element with role alert', () => {
    const toast = toastManager.show('Hello', 'info', 0);
    expect(toast).not.toBeNull();
    expect(toast.getAttribute('role')).toBe('alert');
    expect(toast.textContent).toContain('Hello');
  });

  test('success/error/warning/info shortcuts produce correct class', () => {
    const s = toastManager.success('OK', 0);
    expect(s.className).toContain('toast-success');

    const e = toastManager.error('Fail', 0);
    expect(e.className).toContain('toast-error');

    const w = toastManager.warning('Watch out', 0);
    expect(w.className).toContain('toast-warning');

    const i = toastManager.info('FYI', 0);
    expect(i.className).toContain('toast-info');
  });

  test('dismiss() removes toast after transition delay', () => {
    jest.useFakeTimers();
    const toast = toastManager.show('bye', 'info', 0);
    toastManager.dismiss(toast);

    jest.advanceTimersByTime(300);
    expect(document.querySelector('.toast')).toBeNull();
    jest.useRealTimers();
  });

  test('close button has accessible dismiss label', () => {
    const toast = toastManager.show('closeable', 'info', 0);
    const closeBtn = toast.querySelector('button');
    expect(closeBtn).not.toBeNull();
    expect(closeBtn.getAttribute('aria-label')).toBe('Dismiss');
  });
});

describe('SkeletonLoader', () => {
  test('createPropertyCard returns skeleton HTML', () => {
    const html = SkeletonLoader.createPropertyCard();
    expect(html).toContain('property-card');
    expect(html).toContain('animate-pulse');
    expect(html).toContain('skeleton');
  });

  test('createPropertyGrid creates requested number of cards', () => {
    const html = SkeletonLoader.createPropertyGrid(3);
    const matches = html.match(/property-card/g);
    expect(matches.length).toBe(3);
  });

  test('createTableRow creates correct column count', () => {
    const html = SkeletonLoader.createTableRow(4);
    const matches = html.match(/<td/g);
    expect(matches.length).toBe(4);
  });

  test('show() replaces content and stores original', () => {
    const target = document.createElement('div');
    target.id = 'target';
    target.textContent = 'original';
    document.body.appendChild(target);

    SkeletonLoader.show(target, 'card', 2);

    expect(target.textContent).not.toBe('original');
    expect(target.getAttribute('data-skeleton-original')).toBe('original');
  });

  test('hide() restores original content', () => {
    const target = document.createElement('div');
    target.id = 'target';
    target.textContent = 'original';
    document.body.appendChild(target);

    SkeletonLoader.show(target, 'card', 2);
    SkeletonLoader.hide(target);

    expect(target.textContent).toBe('original');
  });

  test('show/hide with selector string', () => {
    const target = document.createElement('div');
    target.id = 'skel-target';
    target.textContent = 'content';
    document.body.appendChild(target);

    SkeletonLoader.show('#skel-target', 'table', 3);
    expect(target.textContent).not.toBe('content');

    SkeletonLoader.hide('#skel-target');
    expect(target.textContent).toBe('content');
  });

  test('show/hide with null element does not throw', () => {
    expect(() => SkeletonLoader.show('#nonexistent')).not.toThrow();
    expect(() => SkeletonLoader.hide('#nonexistent')).not.toThrow();
  });
});

describe('LoadingButton', () => {
  let btn;

  beforeEach(() => {
    btn = document.createElement('button');
    btn.id = 'btn';
    btn.textContent = 'Submit';
    document.body.appendChild(btn);
  });

  test('start() disables button and shows spinner', () => {
    LoadingButton.start(btn);

    expect(btn.disabled).toBe(true);
    expect(btn.getAttribute('data-loading')).toBe('true');
    expect(btn.textContent).toContain('Loading...');
  });

  test('start() uses custom loading text from data attribute', () => {
    btn.setAttribute('data-loading-text', 'Saving...');
    LoadingButton.start(btn);
    expect(btn.textContent).toContain('Saving...');
  });

  test('stop() restores original content and re-enables', () => {
    LoadingButton.start(btn);
    LoadingButton.stop(btn);

    expect(btn.disabled).toBe(false);
    expect(btn.textContent).toBe('Submit');
    expect(btn.getAttribute('data-loading')).toBeNull();
  });

  test('start/stop with selector string', () => {
    LoadingButton.start('#btn');
    expect(btn.disabled).toBe(true);

    LoadingButton.stop('#btn');
    expect(btn.disabled).toBe(false);
  });

  test('start/stop with null element does not throw', () => {
    expect(() => LoadingButton.start('#nonexistent')).not.toThrow();
    expect(() => LoadingButton.stop('#nonexistent')).not.toThrow();
  });
});

describe('debounce', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  test('calls function after wait period', () => {
    const fn = jest.fn();
    const debounced = debounce(fn, 200);

    debounced();
    expect(fn).not.toHaveBeenCalled();

    jest.advanceTimersByTime(200);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  test('resets timer on repeated calls', () => {
    const fn = jest.fn();
    const debounced = debounce(fn, 200);

    debounced();
    jest.advanceTimersByTime(100);
    debounced();
    jest.advanceTimersByTime(100);
    expect(fn).not.toHaveBeenCalled();

    jest.advanceTimersByTime(100);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  test('passes arguments through', () => {
    const fn = jest.fn();
    const debounced = debounce(fn, 100);

    debounced('a', 'b');
    jest.advanceTimersByTime(100);
    expect(fn).toHaveBeenCalledWith('a', 'b');
  });

  test('defaults to 300ms wait', () => {
    const fn = jest.fn();
    const debounced = debounce(fn);

    debounced();
    jest.advanceTimersByTime(299);
    expect(fn).not.toHaveBeenCalled();

    jest.advanceTimersByTime(1);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});

describe('smoothScrollTo', () => {
  test('does nothing for non-existent target', () => {
    window.scrollTo = jest.fn();
    smoothScrollTo('#nonexistent');
    expect(window.scrollTo).not.toHaveBeenCalled();
  });

  test('scrolls to element with smooth behavior', () => {
    const target = document.createElement('div');
    target.id = 'scroll-target';
    document.body.appendChild(target);
    window.scrollTo = jest.fn();
    window.pageYOffset = 0;

    smoothScrollTo('#scroll-target', 80);
    expect(window.scrollTo).toHaveBeenCalledWith(
      expect.objectContaining({ behavior: 'smooth' })
    );
  });

  test('accepts DOM element directly', () => {
    const target = document.createElement('div');
    document.body.appendChild(target);
    window.scrollTo = jest.fn();
    window.pageYOffset = 0;

    smoothScrollTo(target);
    expect(window.scrollTo).toHaveBeenCalled();
  });
});
