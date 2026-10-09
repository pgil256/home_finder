/**
 * Address suggestions under the lookup box.
 *
 * Follows the ARIA combobox pattern: focus stays in the input, the arrow keys
 * move a highlight through the list, and Enter on a highlighted row opens
 * that parcel. With nothing highlighted, Enter submits the form as usual, so
 * the page works the same without this script.
 */

const DEBOUNCE_MS = 150;
// Matches SUGGEST_MIN_LENGTH on the server.
const MIN_QUERY_LENGTH = 3;

const OPTION_CLASS = 'flex cursor-pointer items-baseline justify-between gap-4 px-4 py-2 text-sm';
const ACTIVE_CLASSES = ['bg-primary-50'];

// The CDN caches each distinct query, so "1029  cha" and "1029 CHA" should be
// one request, not two.
function normalizeQuery(value) {
  return String(value || '').trim().replace(/\s+/g, ' ').toLowerCase();
}

function formatValue(value) {
  return typeof value === 'number' ? `$${Math.round(value).toLocaleString('en-US')}` : '';
}

function statusText(count) {
  if (count === 0) {
    return 'No matching addresses yet. Press Enter to search.';
  }
  const noun = count === 1 ? 'address matches' : 'addresses match';
  return `${count} ${noun}. Use the arrow keys to choose one.`;
}

function initLookupSuggest(root, options = {}) {
  const wrapper = root.querySelector('[data-lookup-suggest]');
  if (!wrapper) {
    return null;
  }
  const input = wrapper.querySelector('input[name="q"]');
  const list = wrapper.querySelector('[role="listbox"]');
  const status = wrapper.querySelector('[role="status"]');
  if (!input || !list) {
    return null;
  }

  const endpoint = wrapper.getAttribute('data-lookup-suggest');
  const fetchImpl = options.fetch || ((...args) => window.fetch(...args));
  const navigate = options.navigate || ((url) => window.location.assign(url));
  const debounceMs = options.debounceMs === undefined ? DEBOUNCE_MS : options.debounceMs;

  const cache = new Map();
  let results = [];
  let activeIndex = -1;
  let timer = null;
  let latestQuery = '';

  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-controls', list.id);
  input.setAttribute('aria-expanded', 'false');

  function setActive(index) {
    activeIndex = index;
    Array.from(list.children).forEach((option, position) => {
      const isActive = position === index;
      option.setAttribute('aria-selected', isActive ? 'true' : 'false');
      ACTIVE_CLASSES.forEach((name) => option.classList.toggle(name, isActive));
      if (isActive && option.scrollIntoView) {
        option.scrollIntoView({ block: 'nearest' });
      }
    });
    if (index >= 0) {
      input.setAttribute('aria-activedescendant', list.children[index].id);
    } else {
      input.removeAttribute('aria-activedescendant');
    }
  }

  function close() {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    setActive(-1);
  }

  function open() {
    if (results.length) {
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }
  }

  function render(rows) {
    results = rows;
    list.textContent = '';
    rows.forEach((row, index) => {
      const option = document.createElement('li');
      option.id = `${list.id}-option-${index}`;
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', 'false');
      option.className = OPTION_CLASS;

      const place = document.createElement('span');
      place.className = 'min-w-0 truncate';
      const address = document.createElement('span');
      address.className = 'font-medium text-charcoal-900';
      address.textContent = row.address;
      place.appendChild(address);
      if (row.city) {
        const city = document.createElement('span');
        city.className = 'text-charcoal-500';
        city.textContent = `, ${row.city}`;
        place.appendChild(city);
      }
      option.appendChild(place);

      const value = document.createElement('span');
      value.className = 'flex-shrink-0 text-charcoal-500';
      value.textContent = formatValue(row.market_value);
      option.appendChild(value);

      // mousedown, not click: the input's blur would close the list first.
      option.addEventListener('mousedown', (event) => {
        event.preventDefault();
        navigate(row.url);
      });
      option.addEventListener('mousemove', () => {
        if (activeIndex !== index) {
          setActive(index);
        }
      });
      list.appendChild(option);
    });
    activeIndex = -1;
    input.removeAttribute('aria-activedescendant');
    if (rows.length) {
      open();
    } else {
      close();
    }
    if (status) {
      status.textContent = statusText(rows.length);
    }
  }

  function clear() {
    results = [];
    list.textContent = '';
    close();
    if (status) {
      status.textContent = '';
    }
  }

  function load(query) {
    latestQuery = query;
    if (cache.has(query)) {
      render(cache.get(query));
      return Promise.resolve();
    }
    return fetchImpl(`${endpoint}?q=${encodeURIComponent(query)}`, { headers: { Accept: 'application/json' } })
      .then((response) => (response.ok ? response.json() : { results: [] }))
      .then((data) => {
        const rows = Array.isArray(data.results) ? data.results : [];
        cache.set(query, rows);
        // A slow answer to an earlier keystroke must not replace a newer one.
        if (query === latestQuery) {
          render(rows);
        }
      })
      .catch(() => {
        // Suggestions are a convenience; the form still submits.
        if (query === latestQuery) {
          clear();
        }
      });
  }

  function onInput() {
    clearTimeout(timer);
    const query = normalizeQuery(input.value);
    if (query.length < MIN_QUERY_LENGTH) {
      latestQuery = '';
      clear();
      return;
    }
    timer = setTimeout(() => load(query), debounceMs);
  }

  function onKeydown(event) {
    if (event.key === 'Escape') {
      if (!list.hidden) {
        // Keep Escape from also clearing the search box.
        event.preventDefault();
        close();
      }
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!results.length) {
        return;
      }
      event.preventDefault();
      if (list.hidden) {
        open();
      }
      const step = event.key === 'ArrowDown' ? 1 : -1;
      // One past either end is "nothing highlighted", back in the typed text.
      let next = activeIndex + step;
      if (next >= results.length) {
        next = -1;
      } else if (next < -1) {
        next = results.length - 1;
      }
      setActive(next);
      return;
    }
    if (event.key === 'Enter' && !list.hidden && activeIndex >= 0) {
      event.preventDefault();
      navigate(results[activeIndex].url);
    }
  }

  input.addEventListener('input', onInput);
  input.addEventListener('keydown', onKeydown);
  input.addEventListener('blur', close);
  input.addEventListener('focus', open);

  return { load, close };
}

if (typeof document !== 'undefined') {
  // The script tag is deferred, so the form is parsed before this runs.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initLookupSuggest(document));
  } else {
    initLookupSuggest(document);
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    MIN_QUERY_LENGTH,
    formatValue,
    initLookupSuggest,
    normalizeQuery,
    statusText,
  };
}
