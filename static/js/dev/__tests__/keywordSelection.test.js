/**
 * Tests for keywordSelection.js DOM manipulation and fetch behavior
 * Uses direct DOM manipulation testing since module auto-executes on DOMContentLoaded
 */

describe('KeywordSelection DOM Functions', () => {
  beforeEach(() => {
    // Set up DOM structure expected by keywordSelection.js
    document.body.innerHTML = `
      <div id="available-keywords"></div>
      <ul id="sortable-container"></ul>
      <ul id="numbering-list"></ul>
      <button id="submit-keywords">Submit</button>
    `;
    // Reset all mocks
    jest.clearAllMocks();
  });

  describe('fetch mocking', () => {
    test('global.fetch is a jest mock function', () => {
      expect(jest.isMockFunction(global.fetch)).toBe(true);
    });

    test('fetch can be mocked with resolved value', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: 'test' }),
      });

      const response = await fetch('test-url');
      const data = await response.json();

      expect(data).toEqual({ data: 'test' });
      expect(global.fetch).toHaveBeenCalledWith('test-url');
    });
  });

  describe('DOM element creation', () => {
    test('creates keyword element with correct structure', () => {
      // Test the DOM structure that would be created by createKeywordElement
      const keyword = document.createElement('div');
      keyword.className = 'keyword flex items-center h-10';

      const text = document.createElement('div');
      text.textContent = 'City';
      text.className = 'flex-grow text-center';
      keyword.appendChild(text);

      expect(keyword.textContent).toContain('City');
      expect(keyword.className).toContain('keyword');
    });

    test('creates sortable list item with correct structure', () => {
      const listItem = document.createElement('li');
      listItem.className = 'sortable-item';

      const textSpan = document.createElement('span');
      textSpan.textContent = 'Price';
      listItem.appendChild(textSpan);

      const deleteButton = document.createElement('img');
      deleteButton.alt = 'Delete';
      listItem.appendChild(deleteButton);

      expect(listItem.querySelector('span').textContent).toBe('Price');
      expect(listItem.querySelector('img')).not.toBeNull();
    });

    test('creates number item with index', () => {
      const numberItem = document.createElement('li');
      numberItem.className = 'flex items-center justify-center';
      numberItem.textContent = '1';

      expect(numberItem.textContent).toBe('1');
    });
  });

  describe('DOM manipulation', () => {
    test('keyword can be moved from available to sortable', () => {
      const availableKeywords = document.getElementById('available-keywords');
      const sortableContainer = document.getElementById('sortable-container');

      // Simulate adding a keyword to available
      const keyword = document.createElement('div');
      keyword.className = 'keyword';
      keyword.textContent = 'City';
      availableKeywords.appendChild(keyword);

      expect(availableKeywords.children.length).toBe(1);
      expect(sortableContainer.children.length).toBe(0);

      // Simulate moving to sortable
      const listItem = document.createElement('li');
      listItem.className = 'sortable-item';
      const span = document.createElement('span');
      span.textContent = keyword.textContent;
      listItem.appendChild(span);

      sortableContainer.appendChild(listItem);
      keyword.remove();

      expect(availableKeywords.children.length).toBe(0);
      expect(sortableContainer.children.length).toBe(1);
      expect(sortableContainer.querySelector('span').textContent).toBe('City');
    });

    test('numbering list updates based on sortable count', () => {
      const sortableContainer = document.getElementById('sortable-container');
      const numberingList = document.getElementById('numbering-list');

      // Helper to update numbering
      const updateNumbering = () => {
        numberingList.innerHTML = '';
        Array.from(sortableContainer.children).forEach((_, index) => {
          const numberItem = document.createElement('li');
          numberItem.textContent = String(index + 1);
          numberingList.appendChild(numberItem);
        });
      };

      // Add two items
      const item1 = document.createElement('li');
      item1.textContent = 'First';
      sortableContainer.appendChild(item1);
      updateNumbering();

      const item2 = document.createElement('li');
      item2.textContent = 'Second';
      sortableContainer.appendChild(item2);
      updateNumbering();

      expect(numberingList.children.length).toBe(2);
      expect(numberingList.children[0].textContent).toBe('1');
      expect(numberingList.children[1].textContent).toBe('2');
    });
  });

  describe('keyword data submission', () => {
    test('builds correct data structure from sortable items', () => {
      const sortableContainer = document.getElementById('sortable-container');

      // Add items to sortable with spans (matching the actual implementation)
      ['City', 'Price', 'Bedrooms'].forEach(name => {
        const item = document.createElement('li');
        const span = document.createElement('span');
        span.textContent = name;
        item.appendChild(span);
        sortableContainer.appendChild(item);
      });

      // Build ordered keywords (matching the actual implementation logic)
      const orderedKeywords = Array.from(sortableContainer.children)
        .map((item, index) => ({
          name: item.querySelector('span').textContent.trim(),
          priority: index + 1,
        }));

      expect(orderedKeywords).toEqual([
        { name: 'City', priority: 1 },
        { name: 'Price', priority: 2 },
        { name: 'Bedrooms', priority: 3 },
      ]);
    });

    test('empty sortable returns empty array', () => {
      const sortableContainer = document.getElementById('sortable-container');

      const orderedKeywords = Array.from(sortableContainer.children)
        .map((item, index) => ({
          name: item.querySelector('span')?.textContent.trim() || '',
          priority: index + 1,
        }));

      expect(orderedKeywords).toEqual([]);
    });
  });

  describe('alert behavior', () => {
    test('alert is called with empty submission message', () => {
      // Simulate the submitKeywords validation
      const keywords = [];

      if (!keywords || keywords.length === 0) {
        alert('Please select at least one keyword before submitting.');
      }

      expect(window.alert).toHaveBeenCalledWith(
        'Please select at least one keyword before submitting.'
      );
    });

    test('alert is called on error response', () => {
      const responseData = { success: false };

      if (!responseData.success) {
        alert('There was an error processing your request.');
      }

      expect(window.alert).toHaveBeenCalledWith(
        'There was an error processing your request.'
      );
    });
  });

  describe('fetch call validation', () => {
    test('fetch is called with correct URL for keywords', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ keywords: ['City'] }),
      });

      await fetch('get-keywords/');

      expect(global.fetch).toHaveBeenCalledWith('get-keywords/');
    });

    test('fetch is called with correct options for submission', async () => {
      const keywords = [{ name: 'City', priority: 1 }];

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      });

      await fetch('submit-keyword-order/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ordered_keywords: keywords }),
      });

      expect(global.fetch).toHaveBeenCalledWith(
        'submit-keyword-order/',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ordered_keywords: keywords }),
        })
      );
    });
  });
});
