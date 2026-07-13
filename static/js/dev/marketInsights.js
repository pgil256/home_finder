const Chart = require('chart.js/auto');

const CHARTS = {
  valueDistribution: 'bar',
  pricePerSqftDistribution: 'bar',
  citySegments: 'bar',
  typeSegments: 'bar',
  yearTrend: 'line',
  valueGapScatter: 'scatter',
};

const TYPE_SEGMENT_LABEL_LIMIT = 24;

function shortenChartLabel(label, maxLength = TYPE_SEGMENT_LABEL_LIMIT) {
  const text = String(label || '');
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1).trimEnd()}\u2026`;
}

function hasPlottableData(payload) {
  if (!payload || !Array.isArray(payload.datasets)) {
    return false;
  }
  return payload.datasets.some((dataset) => Array.isArray(dataset.data) && dataset.data.length > 0);
}

function buildChartConfig(key, payload) {
  const type = CHARTS[key] || 'bar';
  const isScatter = type === 'scatter';
  const isSegment = key === 'citySegments' || key === 'typeSegments';
  const isTypeSegment = key === 'typeSegments';

  const scales = isScatter
    ? {
        x: {
          title: { display: true, text: 'Assessed value' },
          ticks: { callback: (value) => `$${Number(value).toLocaleString()}` },
        },
        y: {
          title: { display: true, text: 'Market value' },
          ticks: { callback: (value) => `$${Number(value).toLocaleString()}` },
        },
      }
    : isTypeSegment
      ? {
          x: {
            beginAtZero: true,
            title: { display: true, text: 'Median market value' },
            ticks: { callback: (value) => Number(value).toLocaleString() },
          },
          y: {
            ticks: {
              autoSkip: false,
              callback(value) {
                return shortenChartLabel(this.getLabelForValue(value));
              },
            },
          },
        }
      : {
          x: {
            ticks: {
              autoSkip: false,
              maxRotation: 45,
              minRotation: 0,
            },
          },
          y: {
            beginAtZero: true,
            ticks: { callback: (value) => Number(value).toLocaleString() },
          },
        };

  return {
    type,
    data: {
      labels: payload.labels || [],
      datasets: payload.datasets || [],
    },
    options: {
      indexAxis: isTypeSegment ? 'y' : 'x',
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        intersect: false,
        mode: isScatter ? 'nearest' : 'index',
      },
      plugins: {
        legend: {
          display: isSegment || isScatter,
          position: 'bottom',
        },
        tooltip: {
          callbacks: {
            label(context) {
              if (isScatter) {
                const point = context.raw || {};
                return `Assessed $${Math.round(point.x || 0).toLocaleString()} · Market $${Math.round(point.y || 0).toLocaleString()}`;
              }
              const parsedValue = isTypeSegment ? context.parsed.x : (context.parsed.y ?? context.parsed);
              const value = Number(parsedValue);
              if (Number.isFinite(value)) {
                return `${context.dataset.label}: ${Math.round(value).toLocaleString()}`;
              }
              return context.dataset.label;
            },
          },
        },
      },
      scales,
    },
  };
}

function readChartPayloads(documentRef = document) {
  const dataEl = documentRef.getElementById('market-insights-charts');
  if (!dataEl) {
    return {};
  }
  try {
    return JSON.parse(dataEl.textContent || '{}');
  } catch (error) {
    console.error('Could not parse market insights chart payloads', error);
    return {};
  }
}

function setChartNote(documentRef, key, payload, hasData) {
  const noteEl = documentRef.querySelector(`[data-chart-note="${key}"]`);
  if (!noteEl) {
    return;
  }
  const meta = payload.meta || {};
  if (!hasData) {
    noteEl.textContent = meta.note || 'No chartable data for this scope.';
    return;
  }
  const parts = [];
  if (meta.chart_sample_size || meta.sample_size) {
    parts.push(`n=${Number(meta.chart_sample_size || meta.sample_size).toLocaleString()}`);
  }
  if (meta.omitted_nulls) {
    parts.push(`${Number(meta.omitted_nulls).toLocaleString()} rows omitted`);
  }
  if (meta.note) {
    parts.push(meta.note);
  }
  noteEl.textContent = parts.join(' · ');
}

function renderMarketInsightsCharts(documentRef = document, ChartClass = Chart) {
  const payloads = readChartPayloads(documentRef);
  Object.entries(CHARTS).forEach(([key]) => {
    const canvas = documentRef.getElementById(`chart-${key}`);
    const payload = payloads[key];
    if (!canvas || !payload) {
      return;
    }

    const hasData = hasPlottableData(payload);
    setChartNote(documentRef, key, payload, hasData);
    if (!hasData) {
      canvas.setAttribute('aria-hidden', 'true');
      return;
    }
    const context = canvas.getContext('2d');
    if (!context) {
      return;
    }
    new ChartClass(context, buildChartConfig(key, payload));
  });
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => {
    renderMarketInsightsCharts(document, Chart);
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    buildChartConfig,
    hasPlottableData,
    readChartPayloads,
    renderMarketInsightsCharts,
    setChartNote,
    shortenChartLabel,
  };
}
