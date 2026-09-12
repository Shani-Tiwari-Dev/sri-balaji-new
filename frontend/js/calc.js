/* Client-side mirror of backend/utils/calc.py — used for instant previews
   in the staff Calculator tab and the Add/Edit slab form before the
   server round-trip confirms the saved values. */

const INCHES_PER_UNIT = { meters: 39.3701, centimeters: 1 / 2.54, feet: 12, inches: 1 };

function calculateSlabArea(length, width, unit, pieces = 1) {
  const factor = INCHES_PER_UNIT[unit] || 12;
  const lengthIn = Number(length) * factor;
  const widthIn = Number(width) * factor;
  const perPieceSqFt = (lengthIn * widthIn) / 144;
  const totalSqFt = Math.round(perPieceSqFt * pieces * 100) / 100;
  const totalSqMeters = Math.round(totalSqFt * 0.092903 * 100) / 100;
  const totalSqCm = Math.round(totalSqFt * 929.03);
  return { totalSqFt, totalSqMeters, totalSqCm };
}

function getRatesInAllUnits(pricePerSqFt) {
  const p = Number(pricePerSqFt) || 0;
  return {
    perSqFt: Math.round(p * 100) / 100,
    perSqMeter: Math.round(p * 10.76391 * 100) / 100,
    perSqCm: Math.round((p / 929.0304) * 1000) / 1000,
  };
}

function formatCurrencyINR(amount) {
  const n = Math.round(Number(amount) || 0);
  return new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", maximumFractionDigits: 0,
  }).format(n);
}
