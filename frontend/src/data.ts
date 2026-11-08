import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api/client";

export const statusLabel: Record<string, string> = {
  exceeds_limit: "Exceeds limit",
  near_limit: "Near limit",
  unallocated_service_rr_4_4: "Unallocated service",
  below_limit: "Below limit",
  candidate_below_limit: "Candidate below limit",
  candidate_near_limit: "Candidate near limit",
  candidate_exceeds_limit: "Candidate exceeds limit",
  not_visible: "Not visible",
  missing_input: "Missing input",
  parameter_missing: "Parameter missing",
  no_criterion: "No criterion",
  special_method_required: "Special method required",
  not_space_station: "Not a space station",
  exceeds_threshold: "Exceeds threshold",
  near_threshold: "Near threshold",
  below_threshold: "Below threshold",
  outside_model_distance: "Outside model distance",
};

export const label = (status: string) => statusLabel[status] ?? status.replace(/_/g, " ");

export interface Issue {
  id: string;
  label: string;
  kind: "Space" | "Terrestrial";
  published?: string;
  counts: Record<string, number>;
  highlights?: { label: string; value?: number; date?: string }[];
  noticesOfConcern: number;
  runId: string;
  regulatoryFramework?: FrameworkItem[];
}

export interface FrameworkItem {
  level: string;
  provision: string;
  role: string;
  printedPage?: number | null;
  pdfPage?: number | null;
  url?: string | null;
  file?: string | null;
}

export interface Linked {
  text: string;
  ref: string | null;
}

export interface NeighbourRow {
  administration: Linked;
  assignment: Linked;
  frequencyMhz: string;
  distanceKm: number | null;
  marginDb: number | null;
  event: string;
  status: string;
  flags: string[];
}

export interface Anomaly {
  type: string;
  dimension: string;
  subject: string;
  reason: string;
}

export interface Station {
  id: string;
  latitude: number;
  longitude: number;
  band: string;
  status: string;
  value: number | null;
  limit: number | null;
  marginDb: number | null;
  distanceKm?: number;
  finnishBand?: string;
  nationalUse?: string;
}

export interface UsageBand {
  band: string;
  kind: "Space" | "Terrestrial";
  nationalUse: string;
  stations: number;
  notices: number;
  cases: number;
  worstMarginDb: number | null;
  worstNoticeKey: string;
  worstNoticeName: string;
  worstRuleId: string;
  statusCounts: Record<string, number>;
}

export interface UsageStation {
  id: string;
  latitude: number;
  longitude: number;
  bands: string[];
  notices: number;
  cases: number;
  worstMarginDb: number | null;
  worstNoticeKey: string;
  worstNoticeName: string;
}

export interface Usage {
  definitions: Record<string, string>;
  bands: UsageBand[];
  stations: UsageStation[];
}

export interface SourceRow {
  dataset: string;
  table: string;
  rows: string;
  sha256: string;
}

export interface Notice {
  key: string;
  priority: number;
  issueId: string;
  kind: "Space" | "Terrestrial";
  noticeId: string;
  administration: string;
  ituCode?: string;
  administrationName: string;
  name: string;
  provision: string;
  publicationDate: string;
  status: string;
  worstMarginDb: number | null;
  measure: string;
  unit: string;
  value: number | null;
  limit: number | null;
  referenceBandwidth: string;
  elevationDeg: number | null;
  distanceKm?: number;
  band: string;
  rule: { id: string; text: string };
  citation: { document: string; provision: string; printedPage: number | null; pdfPage: number | null; url?: string };
  assumptions: string[];
  caveats: string[];
  otherCaseCaveats?: { text: string; cases: number }[];
  worstCaseId?: string;
  responseDeadline?: { date: string; rule: string };
  nationalContext?: { mobileInFinland: string; m4Bands: string[] };
  stationsAffected: number;
  casesOfConcern: number;
  stations: Station[];
  sourceRows: SourceRow[];
}

export interface Change {
  label: string;
  previous: number;
  current: number;
}

export interface Trend {
  issueId?: string;
  anomalies?: Anomaly[];
  anomalyRules?: Record<string, string>;
  neighbourActivity?: { rows: NeighbourRow[]; notes: string[] };
  previous: string;
  current: string;
  administrations: Change[];
  bands: Change[];
}

export interface Assessment {
  generated: string;
  issues: Issue[];
  notices: Notice[];
  usageByIssue?: Record<string, Usage>;
  trends: Trend[];
}

let cache: Promise<Assessment> | null = null;

function load(): Promise<Assessment> {
  cache ??= api.getAssessment();
  return cache;
}

export function useAssessment(): { data: Assessment | null; failed: boolean } {
  const [data, setData] = useState<Assessment | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    load().then(setData, () => setFailed(true));
  }, []);
  return { data, failed };
}

export const DataContext = createContext<Assessment | null>(null);
export const useData = () => useContext(DataContext);

export function findNotice(data: Assessment, key: string) {
  return data.notices.find((n) => n.key === key);
}

export function noticesForStation(data: Assessment, id: string) {
  return data.notices.filter((n) => n.stations.some((s) => s.id === id));
}
