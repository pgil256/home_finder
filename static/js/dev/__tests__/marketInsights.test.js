jest.mock('chart.js/auto', () => jest.fn());

const MockChart = require('chart.js/auto');
const {
  buildChartConfig,
  hasPlottableData,
  readChartPayloads,
  renderMarketInsightsCharts,
  setChartNote,
  shortenChartLabel,
} = require('../marketInsights.js');

describe('marketInsights chart adapter', () => {
  beforeEach(() => {
    MockChart.mockClear();
    HTMLCanvasElement.prototype.getContext = jest.fn(() => ({ canvas: true }));
  });

  test('hasPlottableData detects non-empty datasets', () => {
    expect(hasPlottableData(null)).toBe(false);
    expect(hasPlottableData({ datasets: [{ data: [] }] })).toBe(false);
    expect(hasPlottableData({ datasets: [{ data: [1, 2] }] })).toBe(true);
  });

  test('buildChartConfig creates scatter axes for assessed-vs-market chart', () => {
    const config = buildChartConfig('valueGapScatter', {
      labels: [],
      datasets: [{ label: 'Parcel values', data: [{ x: 1, y: 2 }] }],
    });

    expect(config.type).toBe('scatter');
    expect(config.options.scales.x.title.text).toBe('Assessed value');
    expect(config.options.scales.y.title.text).toBe('Market value');
  });

  test('readChartPayloads parses json_script payload', () => {
    document.body.innerHTML = `
      <script id="market-insights-charts" type="application/json">
        {"valueDistribution":{"labels":["A"],"datasets":[{"data":[1]}],"meta":{}}}
      </script>
    `;

    expect(readChartPayloads(document).valueDistribution.labels).toEqual(['A']);
  });

  test('setChartNote shows empty-data note', () => {
    document.body.innerHTML = '<p data-chart-note="valueDistribution"></p>';

    setChartNote(
      document,
      'valueDistribution',
      { meta: { note: 'Need at least two values.' } },
      false
    );

    expect(document.querySelector('[data-chart-note]').textContent).toBe('Need at least two values.');
  });

  test('renderMarketInsightsCharts renders normal payloads and skips empty canvases', () => {
    document.body.innerHTML = `
      <script id="market-insights-charts" type="application/json">
        {
          "valueDistribution":{"labels":["A"],"datasets":[{"label":"Values","data":[1]}],"meta":{"sample_size":1}},
          "pricePerSqftDistribution":{"labels":[],"datasets":[{"label":"Sqft","data":[]}],"meta":{"note":"No sqft"}}
        }
      </script>
      <p data-chart-note="valueDistribution"></p>
      <p data-chart-note="pricePerSqftDistribution"></p>
      <canvas id="chart-valueDistribution"></canvas>
      <canvas id="chart-pricePerSqftDistribution"></canvas>
    `;

    renderMarketInsightsCharts(document, MockChart);

    expect(MockChart).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-chart-note="valueDistribution"]').textContent).toContain('n=1');
    expect(document.getElementById('chart-pricePerSqftDistribution').getAttribute('aria-hidden')).toBe('true');
  });
});

describe('marketInsights data transformations', () => {
  test('hasPlottableData handles missing/partial datasets', () => {
    expect(hasPlottableData({})).toBe(false);
    expect(hasPlottableData({ datasets: 'nope' })).toBe(false);
    expect(hasPlottableData({ datasets: [{ data: [] }, { data: [3] }] })).toBe(true);
  });

  test('buildChartConfig shows legend and bar axes for segment charts', () => {
    const config = buildChartConfig('citySegments', {
      labels: ['Clearwater'],
      datasets: [{ label: 'Median market value', data: [250000] }],
    });

    expect(config.type).toBe('bar');
    expect(config.options.plugins.legend.display).toBe(true);
    expect(config.options.scales.y.beginAtZero).toBe(true);
    expect(config.options.scales.x.title).toBeUndefined();
  });

  test('buildChartConfig hides legend for plain distribution bars', () => {
    const config = buildChartConfig('valueDistribution', {
      labels: ['A'],
      datasets: [{ label: 'Values', data: [1] }],
    });

    expect(config.options.plugins.legend.display).toBe(false);
  });

  test('property type chart uses readable horizontal bars and shortened axis labels', () => {
    const config = buildChartConfig('typeSegments', {
      labels: ['Condo Conversion - Apartments to Platted Condo'],
      datasets: [{ label: 'Median market value', data: [163092] }],
    });
    const tickContext = {
      getLabelForValue: () => 'Condo Conversion - Apartments to Platted Condo',
    };

    expect(config.options.indexAxis).toBe('y');
    expect(config.options.scales.x.beginAtZero).toBe(true);
    expect(config.options.scales.x.title.text).toBe('Median market value');
    expect(config.options.scales.y.ticks.callback.call(tickContext, 0)).toBe('Condo Conversion - Apar\u2026');
  });

  test('shortenChartLabel preserves short labels and truncates long labels', () => {
    expect(shortenChartLabel('Condominium')).toBe('Condominium');
    expect(shortenChartLabel('Manufactured Home (Co-Op or Share Owned)')).toBe('Manufactured Home (Co-O\u2026');
  });

  test('scatter tooltip formats assessed and market dollars', () => {
    const config = buildChartConfig('valueGapScatter', { labels: [], datasets: [] });
    const label = config.options.plugins.tooltip.callbacks.label({ raw: { x: 12, y: 34 } });

    expect(label).toBe('Assessed $12 · Market $34');
  });

  test('bar tooltip rounds and labels the parsed value', () => {
    const config = buildChartConfig('valueDistribution', { labels: ['A'], datasets: [] });
    const label = config.options.plugins.tooltip.callbacks.label({
      parsed: { y: 12.6 },
      dataset: { label: 'Median market value' },
    });

    expect(label).toBe('Median market value: 13');
  });

  test('horizontal property type tooltip reads the numeric x value', () => {
    const config = buildChartConfig('typeSegments', { labels: ['Condo'], datasets: [] });
    const label = config.options.plugins.tooltip.callbacks.label({
      parsed: { x: 163092, y: 'Condo' },
      dataset: { label: 'Median market value' },
    });

    expect(label).toBe('Median market value: 163,092');
  });

  test('setChartNote joins sample size, omitted rows, and note', () => {
    document.body.innerHTML = '<p data-chart-note="valueDistribution"></p>';

    setChartNote(
      document,
      'valueDistribution',
      { meta: { chart_sample_size: 12, omitted_nulls: 3, note: 'Top 1% trimmed.' } },
      true
    );

    expect(document.querySelector('[data-chart-note]').textContent).toBe('n=12 · 3 rows omitted · Top 1% trimmed.');
  });

  test('readChartPayloads returns empty object when element missing or invalid', () => {
    document.body.innerHTML = '';
    expect(readChartPayloads(document)).toEqual({});

    document.body.innerHTML = '<script id="market-insights-charts" type="application/json">{ not json }</script>';
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {});
    expect(readChartPayloads(document)).toEqual({});
    spy.mockRestore();
  });
});
