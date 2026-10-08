const {
  cashToClose,
  closingCosts,
  fhaMip,
  formatDollars,
  initBudgetSearch,
  initCalculator,
  loanNotes,
  maxPriceForBudget,
  monthlyCost,
  monthlyPI,
  pmi,
  taxAtPrice,
  titlePremium,
} = require('../affordability.js');

// Mirrors apps/analytics/services/lending_config.py.
const lending = {
  limitsYear: 2026,
  conformingLimit: 832750,
  fhaLimit: 541287,
  fhaUpfrontMipPct: 1.75,
  fhaMinDownPct: 3.5,
  fhaAnnualMip: {
    largeLoanOver: 726200,
    long: { standard: [[95, 0.5], [100, 0.55]], large: [[95, 0.7], [100, 0.75]] },
    short: { standard: [[90, 0.15], [100, 0.4]], large: [[78, 0.15], [90, 0.4], [100, 0.65]] },
  },
};

const config = {
  rate: 7.4,
  rateAsOf: 'Oct 8, 2026',
  insuranceRatePct: 1.0,
  budgetTaxRatePct: 1.8,
  lending,
};

describe('loan math', () => {
  test('monthlyPI matches the standard amortization formula', () => {
    expect(monthlyPI(200000, 6, 30)).toBeCloseTo(1199.1, 2);
    expect(monthlyPI(200000, 6, 15)).toBeCloseTo(1687.71, 2);
  });

  test('monthlyPI handles a zero rate and a zero loan', () => {
    expect(monthlyPI(120000, 0, 10)).toBe(1000);
    expect(monthlyPI(0, 6, 30)).toBe(0);
  });

  test('pmi applies only under 20% down and rises with loan-to-value', () => {
    expect(pmi(240000, 80)).toBe(0);
    expect(pmi(190000, 95)).toBeCloseTo(95, 6);
    expect(pmi(194000, 97)).toBeGreaterThan(pmi(194000, 90));
  });

  test('fhaMip charges 1.75% up front and the annual rate for the band', () => {
    const mip = fhaMip(289500, 96.5, 30, lending);
    expect(mip.upfront).toBeCloseTo(5066.25, 2);
    expect(mip.monthly).toBeCloseTo((289500 * 0.0055) / 12, 6);
    expect(fhaMip(270000, 90, 30, lending).monthly).toBeCloseTo((270000 * 0.005) / 12, 6);
  });

  test('fhaMip uses the short-term and large-loan tables', () => {
    expect(fhaMip(200000, 85, 15, lending).monthly).toBeCloseTo((200000 * 0.0015) / 12, 6);
    expect(fhaMip(800000, 96.5, 30, lending).monthly).toBeCloseTo((800000 * 0.0075) / 12, 6);
    expect(fhaMip(0, 96.5, 30, lending)).toEqual({ upfront: 0, monthly: 0 });
  });
});

describe('Florida closing costs', () => {
  test('titlePremium follows the promulgated tiers', () => {
    expect(titlePremium(300000)).toBeCloseTo(575 + 1000, 6);
    expect(titlePremium(1200000)).toBeCloseTo(575 + 4500 + 500, 6);
    expect(titlePremium(10000)).toBe(100);
    expect(titlePremium(0)).toBe(0);
  });

  test('closingCosts charges note stamps, intangible tax and the lender policy', () => {
    const costs = closingCosts({ price: 300000, loanAmount: 240000 });
    expect(costs.docStamps).toBeCloseTo(840, 6);
    expect(costs.intangibleTax).toBeCloseTo(480, 6);
    expect(costs.lenderTitle).toBe(25);
    expect(costs.ownerTitle).toBe(0);
    expect(costs.total).toBeCloseTo(1345, 6);
  });

  test('doc stamps round up to the next $100 of the note', () => {
    expect(closingCosts({ price: 300000, loanAmount: 240050 }).docStamps).toBeCloseTo(840.35, 6);
  });

  test('the owner policy counts only when the buyer pays for it', () => {
    const costs = closingCosts({ price: 300000, loanAmount: 240000, buyerPaysOwnerTitle: true });
    expect(costs.ownerTitle).toBeCloseTo(1575, 6);
    expect(costs.total).toBeCloseTo(1345 + 1575, 6);
  });

  test('a cash purchase has no mortgage taxes or lender policy', () => {
    expect(closingCosts({ price: 300000, loanAmount: 0 }).total).toBe(0);
  });
});

describe('monthlyCost', () => {
  const base = { price: 300000, ratePct: 6, annualTax: 4800, annualInsurance: 3000, monthlyHoa: 150, lending };

  test('adds up principal, interest, tax, insurance and HOA at 20% down', () => {
    const cost = monthlyCost({ ...base, downPct: 20 });
    expect(cost.downPayment).toBe(60000);
    expect(cost.loanAmount).toBe(240000);
    expect(cost.mortgageInsurance).toBe(0);
    expect(cost.total).toBeCloseTo(monthlyPI(240000, 6, 30) + 400 + 250 + 150, 6);
  });

  test('adds PMI on a conventional loan under 20% down', () => {
    const cost = monthlyCost({ ...base, downPct: 5 });
    expect(cost.mortgageInsurance).toBeCloseTo((285000 * 0.006) / 12, 6);
  });

  test('finances the FHA upfront premium into the loan', () => {
    const cost = monthlyCost({ ...base, downPct: 3.5, loanType: 'fha' });
    expect(cost.baseLoan).toBeCloseTo(289500, 6);
    expect(cost.loanAmount).toBeCloseTo(289500 * 1.0175, 6);
    expect(cost.principalAndInterest).toBeCloseTo(monthlyPI(289500 * 1.0175, 6, 30), 6);
    expect(cost.mortgageInsurance).toBeCloseTo((289500 * 0.0055) / 12, 6);
  });

  test('cashToClose adds closing costs, prepaids and other fees to the down payment', () => {
    const inputs = { ...base, downPct: 20, otherCosts: 4000 };
    const cash = cashToClose(monthlyCost(inputs), inputs);
    // First-year insurance plus three months of taxes and insurance.
    expect(cash.prepaids).toBeCloseTo(3000 + 3 * (400 + 250), 6);
    expect(cash.total).toBeCloseTo(60000 + 1345 + 4950 + 4000, 6);
  });

  test('a cash buyer has no escrow to fund', () => {
    const inputs = { ...base, downPct: 100 };
    expect(cashToClose(monthlyCost(inputs), inputs).total).toBe(300000);
  });
});

describe('maxPriceForBudget', () => {
  const assumptions = { downPct: 10, ratePct: 7.4, taxRatePct: 1.8, insuranceRatePct: 1.0, lending };
  const costAt = (price) =>
    monthlyCost({
      price,
      downPct: 10,
      ratePct: 7.4,
      annualTax: price * 0.018,
      annualInsurance: price * 0.01,
      lending,
    }).total;

  test('finds the highest $1,000 step that fits the budget', () => {
    const price = maxPriceForBudget(2800, assumptions);
    expect(price % 1000).toBe(0);
    expect(costAt(price)).toBeLessThanOrEqual(2800);
    expect(costAt(price + 1000)).toBeGreaterThan(2800);
  });

  test('a bigger budget or a lower rate buys more', () => {
    expect(maxPriceForBudget(3500, assumptions)).toBeGreaterThan(maxPriceForBudget(2800, assumptions));
    expect(maxPriceForBudget(2800, { ...assumptions, ratePct: 6 })).toBeGreaterThan(
      maxPriceForBudget(2800, assumptions)
    );
  });

  test('returns 0 when nothing fits', () => {
    expect(maxPriceForBudget(0, assumptions)).toBe(0);
    expect(maxPriceForBudget(400, { ...assumptions, monthlyHoa: 500 })).toBe(0);
  });

  test('caps at the search ceiling', () => {
    expect(maxPriceForBudget(10000000, assumptions)).toBe(10000000);
  });
});

describe('tax and notes', () => {
  test('taxAtPrice moves the estimate by the full millage', () => {
    expect(taxAtPrice(4777, 282885, 282885, 19.9197)).toBe(4777);
    expect(taxAtPrice(4777, 282885, 300000, 19.9197)).toBeCloseTo(4777 + 17115 * 0.0199197, 6);
    expect(taxAtPrice(500, 282885, 100000, 19.9197)).toBe(0);
  });

  test('loanNotes flags jumbo loans and explains PMI', () => {
    const jumbo = monthlyCost({ price: 1200000, downPct: 10, ratePct: 7, lending });
    const notes = loanNotes(jumbo, { loanType: 'conventional', downPct: 10, lending });
    expect(notes.join(' ')).toContain('$832,750');
    expect(notes.join(' ')).toContain('PMI');
  });

  test('loanNotes flags FHA loans over the county limit or under the minimum down', () => {
    const cost = monthlyCost({ price: 700000, downPct: 3, ratePct: 7, loanType: 'fha', lending });
    const notes = loanNotes(cost, { loanType: 'fha', downPct: 3, lending }).join(' ');
    expect(notes).toContain('at least 3.5% down');
    expect(notes).toContain('$541,287');
    expect(notes).toContain('upfront premium');
  });

  test('a plain 20%-down conventional loan needs no notes', () => {
    const cost = monthlyCost({ price: 300000, downPct: 20, ratePct: 7, lending });
    expect(loanNotes(cost, { loanType: 'conventional', downPct: 20, lending })).toEqual([]);
  });

  test('formatDollars rounds to whole dollars', () => {
    expect(formatDollars(1234.56)).toBe('$1,235');
  });
});

describe('parcel page calculator', () => {
  const outputs = [
    'total',
    'principalAndInterest',
    'tax',
    'insurance',
    'mortgageInsurance',
    'hoa',
    'loanAmount',
    'downPayment',
    'stateTaxes',
    'title',
    'prepaids',
    'otherCosts',
    'cashToClose',
  ];

  function render(parcel = { price: 282885, taxHomestead: 4777, taxNoHomestead: 5635, millsTotal: 19.9197 }) {
    document.body.innerHTML = `
      <div id="cost-calculator">
        <input data-calc-input="price" value="${parcel.price}">
        <input data-calc-input="downPct" value="20">
        <select data-calc-input="loanType">
          <option value="conventional">Conventional</option><option value="fha">FHA</option>
        </select>
        <select data-calc-input="termYears"><option value="30">30</option><option value="15">15</option></select>
        <input data-calc-input="ratePct" value="7.40">
        <input data-calc-input="tax">
        ${parcel.taxHomestead === null ? '' : '<input type="checkbox" data-calc-input="homestead" checked>'}
        <input data-calc-input="insurance">
        <input data-calc-input="hoa" value="0">
        <input data-calc-input="otherCosts" value="4000">
        <input type="checkbox" data-calc-input="ownerTitle">
        ${outputs.map((name) => `<span data-calc-output="${name}"></span>`).join('')}
        <div data-calc-row="mortgageInsurance"><span data-calc-label="mortgageInsurance"></span></div>
        <ul data-calc-notes></ul>
      </div>
      <script id="affordability-data" type="application/json">${JSON.stringify({ ...config, parcel })}</script>`;
    return initCalculator(document);
  }

  const input = (name) => document.querySelector(`[data-calc-input="${name}"]`);
  const output = (name) => document.querySelector(`[data-calc-output="${name}"]`).textContent;
  const type = (name, value, eventName = 'input') => {
    input(name).value = value;
    input(name).dispatchEvent(new Event(eventName, { bubbles: true }));
  };

  test('seeds taxes and insurance and renders the payment', () => {
    const { cost } = render();
    expect(input('tax').value).toBe('4777');
    expect(input('insurance').value).toBe('2829');
    expect(output('total')).toBe(formatDollars(cost.total));
    expect(output('downPayment')).toBe('$56,577');
    expect(document.querySelector('[data-calc-row="mortgageInsurance"]').hidden).toBe(true);
  });

  test('taxes follow the price until the visitor types their own', () => {
    render();
    type('price', '300000');
    expect(input('tax').value).toBe('5118');
    type('tax', '6000');
    type('price', '350000');
    expect(input('tax').value).toBe('6000');
    expect(output('tax')).toBe('$500');
  });

  test('unticking homestead switches to the rental estimate', () => {
    render();
    input('homestead').checked = false;
    input('homestead').dispatchEvent(new Event('change', { bubbles: true }));
    expect(input('tax').value).toBe('5635');
  });

  test('parcels that cannot be homesteaded use the one estimate', () => {
    render({ price: 500000, taxHomestead: null, taxNoHomestead: 9960, millsTotal: 19.9197 });
    expect(input('tax').value).toBe('9960');
  });

  test('choosing FHA drops the down payment and shows the premium', () => {
    render();
    type('loanType', 'fha', 'change');
    expect(input('downPct').value).toBe('3.5');
    expect(document.querySelector('[data-calc-row="mortgageInsurance"]').hidden).toBe(false);
    expect(document.querySelector('[data-calc-label="mortgageInsurance"]').textContent).toBe('FHA mortgage insurance');
    expect(document.querySelector('[data-calc-notes]').textContent).toContain('upfront premium');
  });

  test('paying for the owner policy raises cash to close by the promulgated premium', () => {
    const before = render().cash.total;
    input('ownerTitle').checked = true;
    input('ownerTitle').dispatchEvent(new Event('change', { bubbles: true }));
    expect(output('cashToClose')).toBe(formatDollars(before + titlePremium(282885)));
  });

  test('does nothing without the panel or its data', () => {
    document.body.innerHTML = '<div id="cost-calculator"></div>';
    expect(initCalculator(document)).toBeNull();
    document.body.innerHTML =
      '<div id="cost-calculator"></div><script id="affordability-data" type="application/json">{not json</script>';
    expect(initCalculator(document)).toBeNull();
  });
});

describe('budget search', () => {
  function render() {
    document.body.innerHTML = `
      <input id="budget-monthly">
      <select id="budget-down-pct">
        <option value="3.5">3.5%</option><option value="10" selected>10%</option>
      </select>
      <input id="max_value" name="max_price">
      <p id="budget-result"></p>
      <script id="affordability-data" type="application/json">${JSON.stringify(config)}</script>`;
    initBudgetSearch(document);
  }

  const enterBudget = (value) => {
    const field = document.getElementById('budget-monthly');
    field.value = value;
    field.dispatchEvent(new Event('input', { bubbles: true }));
  };

  test('turns a monthly budget into the maximum market value', () => {
    render();
    const changed = jest.fn();
    document.getElementById('max_value').addEventListener('change', changed);
    enterBudget('2800');

    const expected = maxPriceForBudget(2800, {
      downPct: 10,
      ratePct: 7.4,
      taxRatePct: 1.8,
      insuranceRatePct: 1.0,
      lending,
    });
    expect(document.getElementById('max_value').value).toBe(String(expected));
    expect(document.getElementById('budget-result').textContent).toContain(formatDollars(expected));
    expect(changed).toHaveBeenCalled();
  });

  test('3.5% down is priced as an FHA loan', () => {
    render();
    enterBudget('2800');
    const conventional = Number(document.getElementById('max_value').value);
    const down = document.getElementById('budget-down-pct');
    down.value = '3.5';
    down.dispatchEvent(new Event('change', { bubbles: true }));
    expect(document.getElementById('budget-result').textContent).toContain('FHA');
    expect(Number(document.getElementById('max_value').value)).toBeLessThan(conventional);
  });

  test('clearing the budget leaves the price filter alone', () => {
    render();
    enterBudget('2800');
    const price = document.getElementById('max_value').value;
    enterBudget('');
    expect(document.getElementById('max_value').value).toBe(price);
    expect(document.getElementById('budget-result').textContent).toBe('');
  });

  test('says so when the budget is too low', () => {
    render();
    enterBudget('1');
    expect(document.getElementById('max_value').value).toBe('');
    expect(document.getElementById('budget-result').textContent).toContain('too low');
  });

  test('does nothing on pages without the budget field', () => {
    document.body.innerHTML = '';
    expect(initBudgetSearch(document)).toBeNull();
  });
});
