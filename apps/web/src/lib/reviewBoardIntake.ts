import type { CaptureSession } from "../types/capture-inbox";

/**
 * Intake filters answer "which clips reached the board, and when".
 *
 * The batch filter is the precise one: promoting from Capture Inbox only creates a
 * candidate for clips the board has never seen, so a clip re-pushed in today's batch keeps
 * its original creation date. Filtering by batch still finds it; filtering by date does not.
 */
export type IntakeDateChip = "" | "today" | "7d" | "30d" | "custom";

export type IntakeDateBounds = {
  createdAfter?: string;
  createdBefore?: string;
};

export type IntakeFilterState = {
  captureSessionId: string;
  dateChip: IntakeDateChip;
  dateFrom: string;
  dateTo: string;
};

export const EMPTY_INTAKE_FILTERS: IntakeFilterState = {
  captureSessionId: "",
  dateChip: "",
  dateFrom: "",
  dateTo: ""
};

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function shiftDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

function parseDayInput(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const [, year, month, day] = match;
  return new Date(Number(year), Number(month) - 1, Number(day));
}

/**
 * Resolves a chip into a half-open [after, before) range in local time, so a clip added at
 * 23:59 belongs to exactly one bucket.
 */
export function intakeDateRange(
  chip: IntakeDateChip,
  now: Date = new Date(),
  custom?: { from: string; to: string }
): IntakeDateBounds {
  const today = startOfLocalDay(now);
  const tomorrow = shiftDays(today, 1);

  if (chip === "today") {
    return { createdAfter: today.toISOString(), createdBefore: tomorrow.toISOString() };
  }
  if (chip === "7d") {
    return { createdAfter: shiftDays(today, -6).toISOString(), createdBefore: tomorrow.toISOString() };
  }
  if (chip === "30d") {
    return { createdAfter: shiftDays(today, -29).toISOString(), createdBefore: tomorrow.toISOString() };
  }
  if (chip === "custom") {
    const from = custom?.from ? parseDayInput(custom.from) : null;
    const to = custom?.to ? parseDayInput(custom.to) : null;
    return {
      createdAfter: from ? from.toISOString() : undefined,
      // The end day is inclusive for the operator, exclusive for the query.
      createdBefore: to ? shiftDays(to, 1).toISOString() : undefined
    };
  }
  return {};
}

export function intakeFiltersActive(state: IntakeFilterState): boolean {
  if (state.captureSessionId) return true;
  if (state.dateChip === "custom") return Boolean(state.dateFrom || state.dateTo);
  return Boolean(state.dateChip);
}

export function promotedCaptureSessions(sessions: CaptureSession[]): CaptureSession[] {
  return sessions
    .filter((session) => (session.promoted_item_count ?? 0) > 0)
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
}

/**
 * Douyin gives us a sec_uid, never a nickname, and every sec_uid opens with the same
 * "MS4wLjABAAAA" prefix. Only the tail carries signal, so that is all we show.
 */
function profileFingerprint(session: CaptureSession): string | null {
  const identifier =
    session.normalized_profile_identifier?.trim() ||
    session.submitted_profile_url?.trim().split("?")[0].replace(/\/+$/, "").split("/").pop() ||
    "";
  if (!identifier) return null;
  return identifier.length > 6 ? `…${identifier.slice(-6)}` : identifier;
}

function whenLabel(session: CaptureSession, now: Date): string {
  const pushed = new Date(session.created_at);
  if (Number.isNaN(pushed.getTime())) return "Unknown time";
  const time = pushed.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  const sameDay =
    pushed.getFullYear() === now.getFullYear() &&
    pushed.getMonth() === now.getMonth() &&
    pushed.getDate() === now.getDate();
  if (sameDay) return `Today ${time}`;
  return `${pushed.toLocaleDateString(undefined, { day: "2-digit", month: "2-digit" })} ${time}`;
}

export function captureSessionOptionLabel(session: CaptureSession, now: Date = new Date()): string {
  const count = session.promoted_item_count ?? 0;
  const parts = [whenLabel(session, now), `${count} clip${count === 1 ? "" : "s"}`];
  const fingerprint = profileFingerprint(session);
  if (fingerprint) parts.push(fingerprint);
  return parts.join(" · ");
}
