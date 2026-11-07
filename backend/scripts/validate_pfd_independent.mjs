// Independent cross-language validation of exported PFD calculations.
// This script deliberately imports no production Python modules.

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, "../..");
// Optional argument: the issue output folder, e.g. output/ific3074 (the default).
const issueDir = path.resolve(root, process.argv[2] ?? "output/ific3074");
const resultsPath = path.join(issueDir, "pfd-calculations/case_pfd_results.jsonl");
const criteriaPath = path.join(root, "backend/src/app/reference/pfd_criteria.json");
const outputDir = path.join(issueDir, "pfd-validation");
const summaryPath = path.join(outputDir, "independent_validation_summary.json");
const discrepanciesPath = path.join(outputDir, "discrepancies.jsonl");

const EARTH_RADIUS_KM = 6378.137;
const NUMERIC_TOLERANCE_DB = 0.03;
const WORST_MARGIN_TOLERANCE_DB = 0.06;
const SEARCH_STEP_DEG = 0.05;

function sha256(file) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(file));
  return hash.digest("hex");
}

function spreadingDb(distanceKm) {
  return 10 * Math.log10(4 * Math.PI * (distanceKm * 1000) ** 2);
}

function slantRangeKm(elevationDeg, altitudeKm) {
  const e = elevationDeg * Math.PI / 180;
  const radius = EARTH_RADIUS_KM + altitudeKm;
  return Math.sqrt(radius ** 2 - (EARTH_RADIUS_KM * Math.cos(e)) ** 2)
    - EARTH_RADIUS_KM * Math.sin(e);
}

function compileFormula(formula) {
  if (!/^[0-9dXY+*/().\-\slog]+$/.test(formula) || /log(?!10)/.test(formula)) {
    throw new Error(`Unsupported criterion formula: ${formula}`);
  }
  const expression = formula.replaceAll("log10", "Math.log10");
  return new Function("d", "X", "Y", `"use strict"; return (${expression});`);
}

function segmentAt(criterion, angle) {
  return criterion.segments.find(
    segment => segment.elev_min_deg <= angle && angle <= segment.elev_max_deg
  );
}

function limitAt(criterion, angle, parameters) {
  const segment = segmentAt(criterion, angle);
  if (!segment) throw new Error(`No segment for ${criterion.criterion_id} at ${angle}`);
  return segment.compiled(angle, parameters.X, parameters.Y);
}

function objective(criterion, angle, altitudeKm, eirp, parameters) {
  const limit = limitAt(criterion, angle, parameters);
  const distance = slantRangeKm(angle, altitudeKm);
  const value = limit + spreadingDb(distance) - eirp;
  return Number.isFinite(value) ? value : null;
}

function independentWorstMargin(criterion, geometry, eirp, parameters) {
  let best = null;
  for (const config of geometry.configurations) {
    if (!config.visible) continue;
    const top = config.max_elevation_deg;
    for (const segment of criterion.segments) {
      const lower = Math.max(0, segment.elev_min_deg);
      const upper = Math.min(top, segment.elev_max_deg);
      if (lower > upper) continue;
      const points = new Set([lower, upper]);
      for (let angle = lower; angle <= upper; angle += SEARCH_STEP_DEG) {
        points.add(Math.min(angle, upper));
      }
      for (const angle of points) {
        const margin = objective(criterion, angle, config.perigee_km, eirp, parameters);
        if (margin === null) continue;
        if (best === null || margin < best.marginDb) {
          best = { marginDb: margin, angleDeg: angle, config };
        }
      }
    }
  }
  return best;
}

function closeEnough(actual, expected, tolerance) {
  return Math.abs(actual - expected) <= tolerance;
}

function numericPayload(evaluation) {
  if (evaluation.status === "computed") return evaluation;
  if (evaluation.status === "special_method_required") return evaluation.screening_estimate;
  return null;
}

const criteriaDocument = JSON.parse(fs.readFileSync(criteriaPath, "utf8"));
const criteria = new Map();
for (const criterion of criteriaDocument.criteria) {
  criterion.segments = criterion.segments.map(segment => ({
    ...segment,
    compiled: compileFormula(segment.formula),
  }));
  criteria.set(criterion.criterion_id, criterion);
}

fs.mkdirSync(outputDir, { recursive: true });
const discrepancyStream = fs.createWriteStream(discrepanciesPath, { encoding: "utf8" });
const counters = {
  cases: 0,
  numericEvaluations: 0,
  gsoEvaluations: 0,
  nonGsoEvaluations: 0,
  arithmeticChecks: 0,
  worstPointChecks: 0,
  resultClassificationChecks: 0,
  discrepancies: 0,
};
const discrepancyKinds = {};

function discrepancy(caseId, criterionId, kind, detail) {
  counters.discrepancies += 1;
  discrepancyKinds[kind] = (discrepancyKinds[kind] || 0) + 1;
  discrepancyStream.write(JSON.stringify({ case_id: caseId, criterion_id: criterionId, kind, ...detail }) + "\n");
}

const lines = readline.createInterface({
  input: fs.createReadStream(resultsPath, { encoding: "utf8" }),
  crlfDelay: Infinity,
});

for await (const line of lines) {
  if (!line.trim()) continue;
  const record = JSON.parse(line);
  counters.cases += 1;
  for (const evaluation of record.evaluations || []) {
    const numeric = numericPayload(evaluation);
    if (!numeric || !evaluation.emission) continue;
    counters.numericEvaluations += 1;
    const criterion = criteria.get(evaluation.criterion_id);
    const parameters = numeric.parameters_used || {};
    const eirp = evaluation.emission.eirp_in_reference_bandwidth_dbw;
    const angle = numeric.worst_elevation_deg;
    const independentLimit = limitAt(criterion, angle, parameters);
    let independentPfd;
    let independentWorst = null;
    if (record.geometry.orbit === "gso") {
      counters.gsoEvaluations += 1;
      independentPfd = eirp - spreadingDb(record.geometry.slant_range_km);
    } else {
      counters.nonGsoEvaluations += 1;
      independentWorst = independentWorstMargin(criterion, record.geometry, eirp, parameters);
      const config = numeric.orbit_configuration || independentWorst?.config;
      if (!config) {
        discrepancy(record.case_id, evaluation.criterion_id, "orbit_configuration_missing", {});
        continue;
      }
      independentPfd = eirp - spreadingDb(slantRangeKm(angle, config.perigee_km));
    }
    const independentMargin = independentLimit - independentPfd;
    for (const [kind, actual, expected] of [
      ["pfd", numeric.pfd_db, independentPfd],
      ["limit", numeric.limit_db, independentLimit],
      ["margin", numeric.margin_db, independentMargin],
    ]) {
      counters.arithmeticChecks += 1;
      if (!closeEnough(actual, expected, NUMERIC_TOLERANCE_DB)) {
        discrepancy(record.case_id, evaluation.criterion_id, `${kind}_mismatch`, {
          exported: actual, independent: expected,
        });
      }
    }
    if (record.geometry.orbit === "non_gso") {
      const worst = independentWorst;
      counters.worstPointChecks += 1;
      if (!worst || !closeEnough(numeric.margin_db, worst.marginDb, WORST_MARGIN_TOLERANCE_DB)) {
        discrepancy(record.case_id, evaluation.criterion_id, "worst_margin_mismatch", {
          exported_margin_db: numeric.margin_db,
          independent_margin_db: worst?.marginDb,
          exported_angle_deg: numeric.worst_elevation_deg,
          independent_angle_deg: worst?.angleDeg,
        });
      }
    }
  }

  const result = record.result || {};
  if (result.margin_class && typeof result.worst_margin_db === "number") {
    counters.resultClassificationChecks += 1;
    const independentlyClassified = result.worst_margin_db < 0
      ? "exceeds_limit"
      : result.worst_margin_db < 3 ? "near_limit" : "below_limit";
    // Export rounding can put a value within 0.01 dB of a boundary; do not call that a disagreement.
    const nearBoundary = Math.abs(result.worst_margin_db) <= 0.011
      || Math.abs(result.worst_margin_db - 3) <= 0.011;
    if (!nearBoundary && independentlyClassified !== result.margin_class) {
      discrepancy(record.case_id, result.governing_criterion_id, "classification_mismatch", {
        exported: result.margin_class, independent: independentlyClassified,
        margin_db: result.worst_margin_db,
      });
    }
  }
}

await new Promise((resolve, reject) => {
  discrepancyStream.end(resolve);
  discrepancyStream.on("error", reject);
});

const summary = {
  schema_version: 1,
  validator: "independent_javascript_pfd_recalculation",
  validator_version: "1.0.0",
  status: counters.discrepancies === 0 ? "passed" : "failed",
  independence: {
    language: "JavaScript",
    production_language: "Python",
    imports_production_calculation_code: false,
    search_method: `independent ${SEARCH_STEP_DEG}-degree sweep (production uses 0.1 degrees)`,
  },
  tolerances_db: {
    exported_arithmetic: NUMERIC_TOLERANCE_DB,
    independent_non_gso_worst_margin: WORST_MARGIN_TOLERANCE_DB,
  },
  input: {
    results: path.relative(root, resultsPath).replaceAll("\\", "/"),
    results_sha256: sha256(resultsPath),
    criteria: path.relative(root, criteriaPath).replaceAll("\\", "/"),
    criteria_sha256: sha256(criteriaPath),
    criteria_transcription_status: criteriaDocument.transcription.status,
  },
  checks: counters,
  discrepancy_kinds: discrepancyKinds,
  interpretation: {
    validated: "Exported free-space arithmetic, criterion formulas, margins, non-GSO worst-angle search and margin classes.",
    not_validated: [
      "Equivalence with ITU GIBC output.",
      "The AI-transcribed Table 21-4 catalogue against a Traficom-approved golden dataset.",
      "Real antenna pointing, adjacent-band attenuation, terrain, receiver response or harmful-interference impact.",
    ],
    exceedance_meaning: "A pessimistic screening review trigger, not proof of harmful interference or a regulatory violation.",
  },
  outputs: { discrepancies: path.basename(discrepanciesPath) },
};

fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2) + "\n", "utf8");
console.log(JSON.stringify(summary));
process.exitCode = counters.discrepancies === 0 ? 0 : 1;
