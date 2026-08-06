#!/usr/bin/env node
/**
 * Standalone regression check for the weight-unit double-scaling fix in
 * food-entry-ocr-confirm.tsx (consumptionBasisValue / detailColumnValue).
 *
 * Not a test suite (no jest/testing infra exists in this repo yet — see the
 * P0 fix's plan doc/PR description for why that's out of scope here). This
 * inlines the exact formulas from the component as plain functions and
 * asserts them against the real fixtures already used in
 * backend/test_ocr_nutrition_parser.py, so it can be re-run any time with
 * `node app/scripts/verify-consumption-basis-fix.js`.
 */

function truncate2(value) {
  return Math.trunc(value * 100) / 100;
}

// Mirrors submittedValue() in food-entry-ocr-confirm.tsx.
function submittedValue(basisNum, scaleFactor) {
  if (basisNum == null || Number.isNaN(basisNum)) return null;
  return scaleFactor != null ? truncate2(basisNum * scaleFactor) : basisNum;
}

// Mirrors the new consumptionBasisValue() in food-entry-ocr-confirm.tsx.
function consumptionBasisValue(basisNum, scaleFactor, isWeightUnit) {
  if (basisNum == null || Number.isNaN(basisNum)) return null;
  if (isWeightUnit) return basisNum;
  return submittedValue(basisNum, scaleFactor);
}

// Mirrors servingMultiplier's derivation in food-entry-ocr-confirm.tsx.
function servingMultiplier(isWeightUnit, parsedAmount, basisAmountValue) {
  if (isWeightUnit) {
    return basisAmountValue != null && basisAmountValue > 0
      ? parsedAmount / basisAmountValue
      : undefined;
  }
  return parsedAmount;
}

// Mirrors the new detailColumnValue() in food-entry-ocr-confirm.tsx.
function detailColumnValue(basisNum, scaleFactor, isWeightUnit, parsedAmount, basisAmountValue) {
  const basis = consumptionBasisValue(basisNum, scaleFactor, isWeightUnit);
  const mult = servingMultiplier(isWeightUnit, parsedAmount, basisAmountValue);
  if (basis == null || mult == null || Number.isNaN(mult)) return null;
  return truncate2(basis * mult);
}

const WEIGHT_UNITS = new Set(['g', 'ml']);

let failures = 0;
function check(label, actual, expected) {
  const pass = Object.is(actual, expected);
  console.log(`${pass ? 'PASS' : 'FAIL'} — ${label}: got ${actual}, expected ${expected}`);
  if (!pass) failures += 1;
}

console.log('== 감자깡 fixture (per_basis_with_total, basis=100, serving_size_g=30, scale_factor=0.3) ==');
{
  const basisAmountValue = 100;
  const scaleFactor = 0.3; // serving_size_g(30) / basis_amount(100), from ocr_nutrition_parser test fixture
  const sugarPerBasis = 12.0; // sugar_g_per_basis in the same fixture

  // THE BUG: weight-unit mode, ate 50g (not a whole multiple of the 30g serving).
  // Before the fix this produced 1.8 (double-scaled by scale_factor); correct is 6.0.
  const weightUnit = detailColumnValue(sugarPerBasis, scaleFactor, WEIGHT_UNITS.has('g'), 50, basisAmountValue);
  check('weight-unit (g=50) sugar_g — was buggy 1.8, must now be 6.0', weightUnit, 6.0);

  // Count-unit path must be untouched: amount=1 인분 still yields today's value.
  // Note: 12 * 0.3 isn't exact in IEEE754 (3.5999999999999996), and truncate2
  // truncates rather than rounds, so this has always been 3.59, not 3.6 — same
  // floating-point-truncation characteristic already documented in
  // backend/test_ocr_nutrition_parser.py (e.g. 42.59 instead of 42.6). Not a
  // regression from this fix — the count-unit formula itself is unchanged.
  const countUnit = detailColumnValue(sugarPerBasis, scaleFactor, WEIGHT_UNITS.has('인분'), 1, basisAmountValue);
  check('count-unit (인분=1) sugar_g — unchanged from today', countUnit, 3.59);
}

console.log('\n== total_content method (scale_factor always 1.0) — must be a no-op vs. old behavior ==');
{
  const basisAmountValue = 137; // basis_amount_value == total_content_value for this method
  const scaleFactor = 1.0;
  const sugarPerBasis = 16.0; // from real sample_label1.jpg scan

  const weightUnit = detailColumnValue(sugarPerBasis, scaleFactor, true, 68.5, basisAmountValue);
  check('weight-unit (g=68.5, half the 137g package) sugar_g', weightUnit, 8.0);

  const countUnit = detailColumnValue(sugarPerBasis, scaleFactor, false, 1, basisAmountValue);
  check('count-unit (개=1) sugar_g — same result either path since scale_factor=1.0', countUnit, 16.0);
}

console.log('\n== per_serving_with_count method (scale_factor always 1.0) — must be a no-op vs. old behavior ==');
{
  const basisAmountValue = 18.5; // basis_amount_value == serving_size_g for this method
  const scaleFactor = 1.0;
  const sugarPerBasis = 2.0; // from real sample_label2.jpg scan

  const weightUnit = detailColumnValue(sugarPerBasis, scaleFactor, true, 18.5, basisAmountValue);
  check('weight-unit (g=18.5, exactly one serving) sugar_g', weightUnit, 2.0);

  const countUnit = detailColumnValue(sugarPerBasis, scaleFactor, false, 2, basisAmountValue);
  check('count-unit (인분=2) sugar_g', countUnit, 4.0);
}

console.log('\n== unknown method (scale_factor stays null, basis_amount_value stays null) — must not regress ==');
{
  const basisAmountValue = null;
  const scaleFactor = null;
  const sugarPerBasis = 5.0;

  const weightUnit = detailColumnValue(sugarPerBasis, scaleFactor, true, 50, basisAmountValue);
  check('weight-unit (g=50) sugar_g — no basis_amount_value, stays null ("-") same as before', weightUnit, null);

  const countUnit = detailColumnValue(sugarPerBasis, scaleFactor, false, 2, basisAmountValue);
  check('count-unit (인분=2) sugar_g — raw passthrough × count, unchanged from today', countUnit, 10.0);
}

console.log(`\n${failures === 0 ? 'ALL CHECKS PASSED' : `${failures} CHECK(S) FAILED`}`);
process.exit(failures === 0 ? 0 : 1);
