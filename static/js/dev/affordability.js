// Monthly cost and cash-to-close math for the parcel page calculator and the
// budget field on the search form. Everything runs in the browser. Yearly
// constants (loan limits, FHA premiums) and the default rate come from the
// server as JSON; see apps/analytics/services/lending_config.py.

// Rough private mortgage insurance, as [highest loan-to-value %, annual % of
// the loan], for a borrower with good credit. Real quotes depend on credit
// score, so the page labels this as an estimate.
const PMI_BANDS = [
  [85, 0.3],
  [90, 0.45],
  [95, 0.6],
  [100, 0.85],
];

// Florida's promulgated title insurance rates (Rule 69O-186.003), as
// [upper bound of the tier, dollars per $1,000].
const TITLE_RATE_TIERS = [
  [100000, 5.75],
  [1000000, 5.0],
  [5000000, 2.5],
  [10000000, 2.25],
  [Infinity, 2.0],
];
const TITLE_MINIMUM_PREMIUM = 100;
// A lender's policy issued together with an owner's policy, up to the
// owner's amount.
const SIMULTANEOUS_LENDER_POLICY = 25;

const NOTE_DOC_STAMPS_PER_100 = 0.35;
const INTANGIBLE_TAX_RATE = 0.002;

// Lenders usually collect the first year of insurance at closing and start
// the escrow account with a few months of taxes and insurance.
const ESCROW_MONTHS = 3;

const MAX_SEARCH_PRICE = 10000000;

function toNumber(value) {
  const number = typeof value === 'number' ? value : parseFloat(String(value).replace(/[$,\s]/g, ''));
  return Number.isFinite(number) && number > 0 ? number : 0;
}

function rateForBand(bands, ltvPct) {
  const band = bands.find(([maxLtv]) => ltvPct <= maxLtv) || bands[bands.length - 1];
  return band[1];
}

function monthlyPI(loanAmount, annualRatePct, termYears) {
  const payments = termYears * 12;
  if (loanAmount <= 0 || payments <= 0) {
    return 0;
  }
  const monthlyRate = annualRatePct / 100 / 12;
  if (monthlyRate <= 0) {
    return loanAmount / payments;
  }
  return (loanAmount * monthlyRate) / (1 - Math.pow(1 + monthlyRate, -payments));
}

// Monthly PMI on a conventional loan. None at 20% down or more.
function pmi(loanAmount, ltvPct) {
  if (loanAmount <= 0 || ltvPct <= 80) {
    return 0;
  }
  return (loanAmount * rateForBand(PMI_BANDS, ltvPct)) / 100 / 12;
}

// FHA charges a premium up front (usually added to the loan) and another
// every month. Both are figured on the loan before the upfront premium.
function fhaMip(baseLoan, ltvPct, termYears, lending) {
  if (baseLoan <= 0) {
    return { upfront: 0, monthly: 0 };
  }
  const schedule = lending.fhaAnnualMip;
  const byTerm = termYears > 15 ? schedule.long : schedule.short;
  const bands = baseLoan > schedule.largeLoanOver ? byTerm.large : byTerm.standard;
  return {
    upfront: (baseLoan * lending.fhaUpfrontMipPct) / 100,
    monthly: (baseLoan * rateForBand(bands, ltvPct)) / 100 / 12,
  };
}

function titlePremium(amount) {
  if (amount <= 0) {
    return 0;
  }
  let premium = 0;
  let floor = 0;
  TITLE_RATE_TIERS.forEach(([ceiling, perThousand]) => {
    if (amount > floor) {
      premium += ((Math.min(amount, ceiling) - floor) / 1000) * perThousand;
    }
    floor = ceiling;
  });
  return Math.max(TITLE_MINIMUM_PREMIUM, premium);
}

// The formula-driven part of a Florida buyer's closing costs. In Pinellas
// the seller customarily pays for the owner's title policy and the deed
// stamps, so the owner's policy only counts when the buyer has agreed to it.
function closingCosts({ price, loanAmount, buyerPaysOwnerTitle = false }) {
  const financed = loanAmount > 0;
  const docStamps = financed ? Math.ceil(loanAmount / 100) * NOTE_DOC_STAMPS_PER_100 : 0;
  const intangibleTax = financed ? loanAmount * INTANGIBLE_TAX_RATE : 0;
  const lenderTitle = financed ? SIMULTANEOUS_LENDER_POLICY : 0;
  const ownerTitle = buyerPaysOwnerTitle ? titlePremium(price) : 0;
  return {
    docStamps,
    intangibleTax,
    lenderTitle,
    ownerTitle,
    total: docStamps + intangibleTax + lenderTitle + ownerTitle,
  };
}

function monthlyCost({
  price,
  downPct,
  ratePct,
  termYears = 30,
  loanType = 'conventional',
  annualTax = 0,
  annualInsurance = 0,
  monthlyHoa = 0,
  lending,
}) {
  const down = Math.min(Math.max(downPct, 0), 100);
  const downPayment = (price * down) / 100;
  const baseLoan = price - downPayment;
  const ltvPct = 100 - down;

  let loanAmount = baseLoan;
  let mortgageInsurance = 0;
  let upfrontMip = 0;
  if (loanType === 'fha') {
    const mip = fhaMip(baseLoan, ltvPct, termYears, lending);
    upfrontMip = mip.upfront;
    mortgageInsurance = mip.monthly;
    loanAmount = baseLoan + upfrontMip;
  } else {
    mortgageInsurance = pmi(baseLoan, ltvPct);
  }

  const principalAndInterest = monthlyPI(loanAmount, ratePct, termYears);
  const tax = annualTax / 12;
  const insurance = annualInsurance / 12;
  return {
    downPayment,
    baseLoan,
    loanAmount,
    ltvPct,
    upfrontMip,
    principalAndInterest,
    mortgageInsurance,
    tax,
    insurance,
    hoa: monthlyHoa,
    total: principalAndInterest + mortgageInsurance + tax + insurance + monthlyHoa,
  };
}

function cashToClose(cost, { price, annualTax = 0, annualInsurance = 0, otherCosts = 0, buyerPaysOwnerTitle = false }) {
  const closing = closingCosts({ price, loanAmount: cost.loanAmount, buyerPaysOwnerTitle });
  const prepaids = cost.loanAmount > 0 ? annualInsurance + ((annualTax + annualInsurance) / 12) * ESCROW_MONTHS : 0;
  return {
    downPayment: cost.downPayment,
    closing,
    prepaids,
    otherCosts,
    total: cost.downPayment + closing.total + prepaids + otherCosts,
  };
}

// The most expensive home whose monthly cost fits the budget, to the $1,000
// below. Taxes and insurance are taken as a percent of price per year.
function maxPriceForBudget(
  budget,
  { downPct, ratePct, termYears = 30, loanType = 'conventional', taxRatePct, insuranceRatePct, monthlyHoa = 0, lending }
) {
  const costAt = (price) =>
    monthlyCost({
      price,
      downPct,
      ratePct,
      termYears,
      loanType,
      annualTax: (price * taxRatePct) / 100,
      annualInsurance: (price * insuranceRatePct) / 100,
      monthlyHoa,
      lending,
    }).total;

  if (!(budget > 0) || costAt(0) >= budget) {
    return 0;
  }
  if (costAt(MAX_SEARCH_PRICE) <= budget) {
    return MAX_SEARCH_PRICE;
  }
  let low = 0;
  let high = MAX_SEARCH_PRICE;
  while (high - low > 1) {
    const middle = (low + high) / 2;
    if (costAt(middle) <= budget) {
      low = middle;
    } else {
      high = middle;
    }
  }
  return Math.floor(low / 1000) * 1000;
}

// A buyer's tax bill moves with the price. Above the exemptions every extra
// dollar of assessed value is taxed at the full millage.
function taxAtPrice(baseTax, basePrice, price, millsTotal) {
  return Math.max(0, baseTax + ((price - basePrice) * millsTotal) / 1000);
}

function loanNotes(cost, { loanType, downPct, lending }) {
  const notes = [];
  const limit = (amount) => formatDollars(amount);
  if (loanType === 'fha') {
    if (downPct < lending.fhaMinDownPct) {
      notes.push(`FHA loans need at least ${lending.fhaMinDownPct}% down.`);
    }
    if (cost.baseLoan > lending.fhaLimit) {
      notes.push(
        `This loan is over the ${lending.limitsYear} FHA limit for Pinellas County (${limit(lending.fhaLimit)}). You would need a larger down payment or a conventional loan.`
      );
    }
    if (cost.upfrontMip > 0) {
      notes.push(
        `FHA's upfront premium of ${limit(cost.upfrontMip)} is added to the loan. The monthly premium usually lasts for the life of the loan unless you put 10% or more down.`
      );
    }
  } else {
    if (cost.baseLoan > lending.conformingLimit) {
      notes.push(
        `This loan is over the ${lending.limitsYear} conforming limit (${limit(lending.conformingLimit)}), which makes it a jumbo loan. Jumbo rates and down payments differ.`
      );
    }
    if (cost.mortgageInsurance > 0) {
      notes.push(
        'PMI here assumes good credit; your quote depends on your score. It comes off once you reach 20% equity.'
      );
    }
  }
  return notes;
}

function formatDollars(amount) {
  return `$${Math.round(amount).toLocaleString('en-US')}`;
}

function readConfig(documentRef) {
  const node = documentRef.getElementById('affordability-data');
  if (!node) {
    return null;
  }
  try {
    return JSON.parse(node.textContent);
  } catch (error) {
    return null;
  }
}

function initCalculator(documentRef = document) {
  const root = documentRef.getElementById('cost-calculator');
  const config = readConfig(documentRef);
  if (!root || !config || !config.parcel) {
    return null;
  }
  const { parcel, lending } = config;
  const field = (name) => root.querySelector(`[data-calc-input="${name}"]`);
  const fields = {
    price: field('price'),
    downPct: field('downPct'),
    loanType: field('loanType'),
    ratePct: field('ratePct'),
    termYears: field('termYears'),
    homestead: field('homestead'),
    tax: field('tax'),
    insurance: field('insurance'),
    hoa: field('hoa'),
    otherCosts: field('otherCosts'),
    ownerTitle: field('ownerTitle'),
  };
  // Taxes and insurance follow the price until the visitor types their own.
  const edited = { tax: false, insurance: false };

  const baseTax = () =>
    fields.homestead && fields.homestead.checked && parcel.taxHomestead !== null
      ? parcel.taxHomestead
      : parcel.taxNoHomestead;

  function update() {
    const price = toNumber(fields.price.value);
    if (!edited.tax) {
      fields.tax.value = Math.round(taxAtPrice(baseTax(), parcel.price, price, parcel.millsTotal));
    }
    if (!edited.insurance) {
      fields.insurance.value = Math.round((price * config.insuranceRatePct) / 100);
    }
    const inputs = {
      price,
      downPct: toNumber(fields.downPct.value),
      ratePct: toNumber(fields.ratePct.value),
      termYears: toNumber(fields.termYears.value) || 30,
      loanType: fields.loanType.value,
      annualTax: toNumber(fields.tax.value),
      annualInsurance: toNumber(fields.insurance.value),
      monthlyHoa: toNumber(fields.hoa.value),
      otherCosts: toNumber(fields.otherCosts.value),
      buyerPaysOwnerTitle: Boolean(fields.ownerTitle && fields.ownerTitle.checked),
      lending,
    };
    const cost = monthlyCost(inputs);
    const cash = cashToClose(cost, inputs);
    const outputs = {
      total: cost.total,
      principalAndInterest: cost.principalAndInterest,
      tax: cost.tax,
      insurance: cost.insurance,
      mortgageInsurance: cost.mortgageInsurance,
      hoa: cost.hoa,
      loanAmount: cost.loanAmount,
      downPayment: cash.downPayment,
      stateTaxes: cash.closing.docStamps + cash.closing.intangibleTax,
      title: cash.closing.lenderTitle + cash.closing.ownerTitle,
      prepaids: cash.prepaids,
      otherCosts: cash.otherCosts,
      cashToClose: cash.total,
    };
    Object.entries(outputs).forEach(([name, amount]) => {
      root.querySelectorAll(`[data-calc-output="${name}"]`).forEach((node) => {
        node.textContent = formatDollars(amount);
      });
    });
    root.querySelectorAll('[data-calc-row="mortgageInsurance"]').forEach((row) => {
      row.hidden = cost.mortgageInsurance <= 0;
    });
    root.querySelectorAll('[data-calc-label="mortgageInsurance"]').forEach((node) => {
      node.textContent = inputs.loanType === 'fha' ? 'FHA mortgage insurance' : 'PMI';
    });

    const notes = root.querySelector('[data-calc-notes]');
    if (notes) {
      notes.textContent = '';
      loanNotes(cost, inputs).forEach((text) => {
        const item = documentRef.createElement('li');
        item.textContent = text;
        notes.appendChild(item);
      });
    }
    return { cost, cash };
  }

  ['tax', 'insurance'].forEach((name) => {
    fields[name].addEventListener('input', () => {
      edited[name] = true;
    });
  });
  if (fields.homestead) {
    // Choosing a tax scenario asks for the estimate again.
    fields.homestead.addEventListener('change', () => {
      edited.tax = false;
    });
  }
  fields.loanType.addEventListener('change', () => {
    // FHA's selling point is the low down payment, so start there.
    if (fields.loanType.value === 'fha' && toNumber(fields.downPct.value) >= 20) {
      fields.downPct.value = lending.fhaMinDownPct;
    }
  });
  root.addEventListener('input', update);
  root.addEventListener('change', update);
  return update();
}

function initBudgetSearch(documentRef = document) {
  const budgetField = documentRef.getElementById('budget-monthly');
  const downField = documentRef.getElementById('budget-down-pct');
  const maxPriceField = documentRef.getElementById('max_value');
  const result = documentRef.getElementById('budget-result');
  const config = readConfig(documentRef);
  if (!budgetField || !downField || !maxPriceField || !config) {
    return null;
  }

  function update() {
    const budget = toNumber(budgetField.value);
    if (!budget) {
      if (result) {
        result.textContent = '';
      }
      return null;
    }
    const downPct = toNumber(downField.value);
    const loanType = downPct < 5 ? 'fha' : 'conventional';
    const price = maxPriceForBudget(budget, {
      downPct,
      ratePct: config.rate,
      loanType,
      taxRatePct: config.budgetTaxRatePct,
      insuranceRatePct: config.insuranceRatePct,
      lending: config.lending,
    });
    maxPriceField.value = price || '';
    maxPriceField.dispatchEvent(new Event('change'));
    if (result) {
      result.textContent = price
        ? `About ${formatDollars(price)} with ${downPct}% down on a 30-year ${loanType === 'fha' ? 'FHA' : 'conventional'} loan at ${config.rate}%. Maximum market value is set to match.`
        : 'That budget is too low for a mortgage at these assumptions.';
    }
    return price;
  }

  budgetField.addEventListener('input', update);
  downField.addEventListener('change', update);
  return update;
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => {
    initCalculator(document);
    initBudgetSearch(document);
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
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
  };
}
