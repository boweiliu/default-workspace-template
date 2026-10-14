/**
 * What a person is told when a request to the workspace fails: a sentence of ours on screen, and everything
 * underneath it (a status, the server's own text) behind "See details" rather than on the visible line.
 */

/** Whether a failed request only read something (nothing it did can have changed) or asked for a change, which an
 *  unanswered request may have carried out anyway. */
export type RequestKind = "read" | "change";

/** A failure as a surface shows it. */
export interface Failure {
  readonly message: string;
  /** What goes behind "See details"; null when there is nothing beyond the sentence. */
  readonly details: string | null;
  /** The sentence is one of ours that ends by asking for a bug report, so the surface offers "Report a bug". */
  readonly isReportable: boolean;
}

/** What Imbue Studio's forward proxy and the workspace's own front door answer when the server behind them did not.
 *  Neither tells whether the request reached the server first. */
export const GATEWAY_STATUSES: ReadonlySet<number> = new Set([502, 503, 504]);

export const READ_NOT_ANSWERED = "The workspace didn't answer. Try again in a moment.";
// Never "nothing was changed": a gateway status can arrive after the request was carried out, and a connection that
// dropped after the request was sent looks the same as one that never opened.
export const CHANGE_NOT_ANSWERED =
  "The workspace didn't answer, so Imbue Studio can't tell whether this went through.";

const REPORT_A_BUG_ENDING = "Try again. If this persists, report a bug.";

/** The sentence for a request nothing answered (a gateway status, a dropped connection, a timeout). */
export function notAnsweredSentence(kind: RequestKind): string {
  return kind === "read" ? READ_NOT_ANSWERED : CHANGE_NOT_ANSWERED;
}

/** The fallback for a failure with no explanation of its own: what failed, then the bug-report ending. */
export function fallbackSentence(whatFailed: string): string {
  return `${whatFailed}. ${REPORT_A_BUG_ENDING}`;
}

/** A failure that carries no explanation of its own, as the fallback sentence for ``whatFailed``. */
export function fallbackFailure(whatFailed: string, details: string | null = null): Failure {
  return { message: fallbackSentence(whatFailed), details, isReportable: true };
}

/** The non-empty lines of a "See details" text, joined; null when every one is empty. */
export function joinDetails(lines: readonly (string | null | undefined)[]): string | null {
  const kept = lines.map((line) => (line ?? "").trim()).filter((line) => line !== "");
  return kept.length === 0 ? null : kept.join("\n");
}

/** ``value`` trimmed when it is a string with something in it; null otherwise. */
export function nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}
