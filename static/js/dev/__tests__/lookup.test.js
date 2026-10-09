const { formatValue, initLookupSuggest, normalizeQuery, statusText } = require('../lookup.js');

const ROWS = [
  { parcel_id: '1', address: '1029 CHARLES ST', city: 'Clearwater', market_value: 1032109, url: '/analytics/property/1/' },
  { parcel_id: '2', address: '1029 CHAUCER RD', city: 'Dunedin', market_value: null, url: '/analytics/property/2/' },
  { parcel_id: '3', address: '1029 CHERRY LN', city: '', market_value: 250000, url: '/analytics/property/3/' },
];

function renderForm() {
  document.body.innerHTML = `
    <form>
      <div data-lookup-suggest="/lookup/suggest/">
        <input type="search" id="lookup-q" name="q">
        <ul id="lookup-suggestions" role="listbox" hidden></ul>
        <p role="status"></p>
      </div>
    </form>
  `;
  return {
    input: document.getElementById('lookup-q'),
    list: document.getElementById('lookup-suggestions'),
    status: document.querySelector('[role="status"]'),
  };
}

function respondWith(rows) {
  return jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ results: rows }) }));
}

function press(input, key) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
  input.dispatchEvent(event);
  return event;
}

async function openWith(rows = ROWS) {
  const elements = renderForm();
  const navigate = jest.fn();
  const fetch = respondWith(rows);
  const suggest = initLookupSuggest(document, { fetch, navigate, debounceMs: 0 });
  await suggest.load('1029 ch');
  return { ...elements, navigate, fetch, suggest };
}

describe('helpers', () => {
  test('normalizeQuery collapses case and spacing so equal queries share a cache entry', () => {
    expect(normalizeQuery('  1029   CHA ')).toBe('1029 cha');
    expect(normalizeQuery(null)).toBe('');
  });

  test('formatValue shows dollars, or nothing when the county lists no value', () => {
    expect(formatValue(1032109)).toBe('$1,032,109');
    expect(formatValue(null)).toBe('');
  });

  test('statusText announces the count', () => {
    expect(statusText(0)).toMatch(/No matching addresses/);
    expect(statusText(1)).toMatch(/^1 address matches/);
    expect(statusText(3)).toMatch(/^3 addresses match/);
  });
});

describe('initLookupSuggest', () => {
  test('does nothing on a page without the lookup form', () => {
    document.body.innerHTML = '<p>No form here</p>';
    expect(initLookupSuggest(document)).toBeNull();
  });

  test('marks the input as a combobox that controls the list', () => {
    const { input } = renderForm();
    initLookupSuggest(document, { fetch: respondWith([]) });

    expect(input.getAttribute('role')).toBe('combobox');
    expect(input.getAttribute('aria-controls')).toBe('lookup-suggestions');
    expect(input.getAttribute('aria-expanded')).toBe('false');
  });

  test('lists the matches as options and announces them', async () => {
    const { input, list, status, fetch } = await openWith();

    expect(fetch).toHaveBeenCalledWith('/lookup/suggest/?q=1029%20ch', expect.anything());
    expect(list.hidden).toBe(false);
    expect(input.getAttribute('aria-expanded')).toBe('true');
    const options = list.querySelectorAll('[role="option"]');
    expect(options).toHaveLength(3);
    expect(options[0].textContent).toContain('1029 CHARLES ST, Clearwater');
    expect(options[0].textContent).toContain('$1,032,109');
    expect(status.textContent).toMatch(/^3 addresses match/);
  });

  test('renders addresses as text, never as markup', async () => {
    const { list } = await openWith([{ ...ROWS[0], address: '<img src=x onerror=alert(1)>' }]);

    expect(list.querySelector('img')).toBeNull();
    expect(list.textContent).toContain('<img src=x');
  });

  test('arrow keys move the highlight and wrap through the typed text', async () => {
    const { input, list } = await openWith();
    const options = list.children;

    press(input, 'ArrowDown');
    expect(input.getAttribute('aria-activedescendant')).toBe(options[0].id);
    expect(options[0].getAttribute('aria-selected')).toBe('true');

    press(input, 'ArrowDown');
    press(input, 'ArrowDown');
    expect(input.getAttribute('aria-activedescendant')).toBe(options[2].id);
    expect(options[0].getAttribute('aria-selected')).toBe('false');

    press(input, 'ArrowDown');
    expect(input.hasAttribute('aria-activedescendant')).toBe(false);

    press(input, 'ArrowUp');
    expect(input.getAttribute('aria-activedescendant')).toBe(options[2].id);
  });

  test('Enter on a highlighted row opens that parcel instead of submitting', async () => {
    const { input, navigate } = await openWith();

    press(input, 'ArrowDown');
    press(input, 'ArrowDown');
    const event = press(input, 'Enter');

    expect(event.defaultPrevented).toBe(true);
    expect(navigate).toHaveBeenCalledWith('/analytics/property/2/');
  });

  test('Enter with nothing highlighted leaves the form to submit', async () => {
    const { input, navigate } = await openWith();

    const event = press(input, 'Enter');

    expect(event.defaultPrevented).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });

  test('Escape closes the list and clears the highlight', async () => {
    const { input, list } = await openWith();
    press(input, 'ArrowDown');

    const event = press(input, 'Escape');

    expect(event.defaultPrevented).toBe(true);
    expect(list.hidden).toBe(true);
    expect(input.getAttribute('aria-expanded')).toBe('false');
    expect(input.hasAttribute('aria-activedescendant')).toBe(false);
  });

  test('arrow down reopens a closed list', async () => {
    const { input, list } = await openWith();
    press(input, 'Escape');

    press(input, 'ArrowDown');

    expect(list.hidden).toBe(false);
  });

  test('pressing the mouse on a row opens that parcel', async () => {
    const { list, navigate } = await openWith();

    list.children[2].dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));

    expect(navigate).toHaveBeenCalledWith('/analytics/property/3/');
  });

  test('leaving the box closes the list', async () => {
    const { input, list } = await openWith();

    input.dispatchEvent(new Event('blur'));

    expect(list.hidden).toBe(true);
  });

  test('no matches keeps the list closed and says so', async () => {
    const { list, status } = await openWith([]);

    expect(list.hidden).toBe(true);
    expect(status.textContent).toMatch(/No matching addresses/);
  });

  test('a repeated query is answered from memory', async () => {
    const { fetch, suggest } = await openWith();

    await suggest.load('1029 ch');

    expect(fetch).toHaveBeenCalledTimes(1);
  });

  test('a slow answer to an earlier keystroke does not replace a newer one', async () => {
    const { list } = renderForm();
    let answerFirst;
    const fetch = jest
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            answerFirst = resolve;
          })
      )
      .mockImplementationOnce(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ results: [ROWS[1]] }) }));
    const suggest = initLookupSuggest(document, { fetch, debounceMs: 0 });

    const first = suggest.load('1029 ch');
    await suggest.load('1029 cha');
    answerFirst({ ok: true, json: () => Promise.resolve({ results: ROWS }) });
    await first;

    expect(list.children).toHaveLength(1);
    expect(list.textContent).toContain('1029 CHAUCER RD');
  });

  test('a failed request leaves a working form with no list', async () => {
    const { list } = renderForm();
    const fetch = jest.fn(() => Promise.reject(new Error('offline')));
    const suggest = initLookupSuggest(document, { fetch, debounceMs: 0 });

    await suggest.load('1029 ch');

    expect(list.hidden).toBe(true);
  });

  describe('typing', () => {
    beforeEach(() => jest.useFakeTimers());
    afterEach(() => jest.useRealTimers());

    function type(input, value) {
      input.value = value;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    test('waits for a pause, then asks once for the latest text', () => {
      const { input } = renderForm();
      const fetch = respondWith(ROWS);
      initLookupSuggest(document, { fetch });

      type(input, '102');
      type(input, '1029');
      type(input, '1029 Ch');
      expect(fetch).not.toHaveBeenCalled();

      jest.advanceTimersByTime(150);
      expect(fetch).toHaveBeenCalledTimes(1);
      expect(fetch.mock.calls[0][0]).toBe('/lookup/suggest/?q=1029%20ch');
    });

    test('does not ask for fewer than three characters', () => {
      const { input } = renderForm();
      const fetch = respondWith(ROWS);
      initLookupSuggest(document, { fetch });

      type(input, '10');
      jest.advanceTimersByTime(500);

      expect(fetch).not.toHaveBeenCalled();
    });
  });
});
