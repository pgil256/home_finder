jest.mock('chart.js/auto', () => jest.fn());

const MockChart = require('chart.js/auto');
const {
  buildChartConfig,
  hasPlottableData,
  readChartPayloads,
  renderMarketInsightsCharts,
  setChartNote,
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
