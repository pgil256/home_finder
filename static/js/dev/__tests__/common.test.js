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
  readSavedHomes,
  compareUrl,
  updateSavedLinks,
  toggleSavedHome,
  initComparePage,
  submitWithCsrfToken,
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

describe('saved homes', () => {
  const HOUSE = '36-30-16-78588-003-0060';
  const CONDO = '07-31-15-00000-000-0010';
  const save = (ids) => window.localStorage.setItem('savedProperties', JSON.stringify(ids));

  beforeEach(() => {
    window.localStorage.clear();
  });

  test('reads the list the Save button writes', () => {
    expect(readSavedHomes()).toEqual([]);
    save([HOUSE, CONDO]);
    expect(readSavedHomes()).toEqual([HOUSE, CONDO]);
  });

  test('treats unreadable storage as an empty list', () => {
    window.localStorage.setItem('savedProperties', '{not json');
    expect(readSavedHomes()).toEqual([]);
    window.localStorage.setItem('savedProperties', '{"a": 1}');
    expect(readSavedHomes()).toEqual([]);
    save([HOUSE, 7, null, '']);
    expect(readSavedHomes()).toEqual([HOUSE]);
  });

  test('builds the compare link from the list', () => {
    expect(compareUrl('/analytics/compare/', [])).toBe('/analytics/compare/');
    expect(compareUrl('/analytics/compare/', [HOUSE, CONDO])).toBe(`/analytics/compare/?ids=${HOUSE},${CONDO}`);
    expect(compareUrl('/analytics/compare/', ['a&b'])).toBe('/analytics/compare/?ids=a%26b');
  });

  test('saving and removing a home updates the header link', () => {
    document.body.innerHTML =
      '<a href="/analytics/compare/" data-saved-link="/analytics/compare/">Saved<span data-saved-count></span></a>';
    const link = document.querySelector('a');

    updateSavedLinks();
    expect(link.textContent).toBe('Saved');

    expect(toggleSavedHome(HOUSE)).toBe(true);
    expect(toggleSavedHome(CONDO)).toBe(true);
    expect(link.textContent).toBe('Saved (2)');
    expect(link.getAttribute('href')).toBe(`/analytics/compare/?ids=${HOUSE},${CONDO}`);

    expect(toggleSavedHome(HOUSE)).toBe(false);
    expect(readSavedHomes()).toEqual([CONDO]);
    expect(link.textContent).toBe('Saved (1)');
    expect(link.getAttribute('href')).toBe(`/analytics/compare/?ids=${CONDO}`);
  });

  describe('compare page', () => {
    const page = (inner) => {
      document.body.innerHTML = `<div data-compare-url="/analytics/compare/">${inner}</div>`;
    };

    test('an empty page loads this browser\'s saved homes', () => {
      save([HOUSE, CONDO]);
      page('<div data-compare-empty></div>');
      const navigate = jest.fn();
      initComparePage(navigate);
      expect(navigate).toHaveBeenCalledWith(`/analytics/compare/?ids=${HOUSE},${CONDO}`);
    });

    test('an empty page stays put when nothing is saved', () => {
      page('<div data-compare-empty></div>');
      const navigate = jest.fn();
      initComparePage(navigate);
      expect(navigate).not.toHaveBeenCalled();
    });

    test('a page of unknown homes does not reload itself', () => {
      save([HOUSE]);
      page('<div>These homes are gone</div>');
      const navigate = jest.fn();
      initComparePage(navigate);
      expect(navigate).not.toHaveBeenCalled();
    });

    test('Remove forgets the home and keeps the other columns', () => {
      save([HOUSE, CONDO, 'not-on-this-page']);
      page(`<button data-unsave="${HOUSE}"></button><button data-unsave="${CONDO}"></button>`);
      const navigate = jest.fn();
      initComparePage(navigate);

      document.querySelector(`[data-unsave="${HOUSE}"]`).click();

      expect(readSavedHomes()).toEqual([CONDO, 'not-on-this-page']);
      expect(navigate).toHaveBeenCalledWith(`/analytics/compare/?ids=${CONDO}`);
    });

    test('does nothing on other pages', () => {
      save([HOUSE]);
      document.body.innerHTML = '<div data-compare-empty></div>';
      const navigate = jest.fn();
      initComparePage(navigate);
      expect(navigate).not.toHaveBeenCalled();
    });
  });
});

describe('CSRF token on demand', () => {
  let form;

  beforeEach(() => {
    document.body.innerHTML = `
      <form method="post" action="/analytics/property/1/refresh/" data-csrf-url="/analytics/csrf/">
        <button type="submit">Refresh</button>
      </form>`;
    form = document.querySelector('form');
    form.submit = jest.fn();
    window.Toast = { error: jest.fn() };
  });

  test('fetches a token, adds it to the form and submits', async () => {
    const fetchImpl = jest.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ csrfToken: 'abc123' }) });

    await submitWithCsrfToken(form, fetchImpl);

    expect(fetchImpl).toHaveBeenCalledWith('/analytics/csrf/', expect.objectContaining({ credentials: 'same-origin' }));
    expect(form.querySelector('input[name="csrfmiddlewaretoken"]').value).toBe('abc123');
    expect(form.submit).toHaveBeenCalledTimes(1);
  });

  test('re-enables the button and says so when the token cannot be fetched', async () => {
    const button = form.querySelector('button');
    LoadingButton.start(button);

    await submitWithCsrfToken(form, jest.fn().mockResolvedValue({ ok: false, status: 503 }));

    expect(form.submit).not.toHaveBeenCalled();
    expect(button.disabled).toBe(false);
    expect(window.Toast.error).toHaveBeenCalled();
  });
});
