/**
 * How the desktop words a failed request on its own surfaces (a toast, a dialog's line, the launcher, the
 * backdrop): a sentence the shell wrote for people, or the one a request nothing answered gets, stands as it is;
 * any other reason (the shell's developer text, a parser's, a bare status) goes behind "See details" under the
 * surface's own sentence for what failed. A sentence that asks for a bug report carries "Report a bug".
 */

import { HttpError } from "@imbue/workspace-ui/src/models/http";
import { asksForBugReport, isNotAnsweredSentence, joinDetails } from "@imbue/workspace-ui/src/models/failure";
import { describeRequestFailure } from "@imbue/workspace-ui/src/models/request-error";
import { REPORT_A_BUG_LABEL, openBugReport } from "@imbue/workspace-ui/src/report-bug";
import type { AppRecord } from "./records";
import type { ToastAction } from "./Toasts";

/** A failure as a desktop surface shows it. */
export interface FailureNotice {
  readonly message: string;
  /** What goes behind "See details"; null when there is nothing beyond the sentence. */
  readonly details: string | null;
  /** Its buttons, in order ("Report a bug" last). */
  readonly actions: readonly ToastAction[];
}

/** What the shell's refusals name with ``kind`` (desktop contracts.md, the error body), for the desktop to word
 *  with what only it holds. */
export type RefusalKind =
  "app_unavailable" | "launch_path_gone" | "window_gone" | "launch_failed" | "out_of_space" | "not_saved";

const REFUSAL_KINDS: ReadonlySet<string> = new Set<RefusalKind>([
  "app_unavailable",
  "launch_path_gone",
  "window_gone",
  "launch_failed",
  "out_of_space",
  "not_saved",
]);

/** "Report a bug", opening the bug report with ``reportBug``. */
export function reportBugAction(reportBug: () => void = openBugReport): ToastAction {
  return { label: REPORT_A_BUG_LABEL, run: reportBug };
}

/** What a window, a shortcut, or a launcher row says of an app that is not running and that the workspace does not
 *  start on a request: one it does not run itself, or one it treats as part of how it runs. */
export function stoppedSentence(app: AppRecord): string {
  return app.program === "" ? `${app.display_name} isn't running.` : `${app.display_name} is not running right now.`;
}

/** The kind of refusal the shell answered ``error`` with, or null for any other failure. */
export function refusalKindOf(error: unknown): RefusalKind | null {
  if (!(error instanceof HttpError)) return null;
  const kind = error.body?.kind;
  return typeof kind === "string" && REFUSAL_KINDS.has(kind) ? (kind as RefusalKind) : null;
}

/** ``message`` with its "Report a bug" (which runs ``reportBug``) when it asks for one, after ``actions``. */
export function noticeOf(
  message: string,
  details: string | null,
  actions: readonly ToastAction[] = [],
  reportBug: () => void = openBugReport,
): FailureNotice {
  return { message, details, actions: asksForBugReport(message) ? [...actions, reportBugAction(reportBug)] : actions };
}

/**
 * ``error`` as a surface whose own sentence for the failure is ``fallback`` shows it: the shell's sentence for
 * people, or the no-answer sentence, as it is; otherwise ``fallback``, with the reason it replaces behind the
 * details. ``actions`` come before "Report a bug", which runs ``reportBug``.
 */
export function failureNotice(
  fallback: string,
  error: unknown,
  actions: readonly ToastAction[] = [],
  reportBug: () => void = openBugReport,
): FailureNotice {
  const failure = describeRequestFailure(error);
  if (failure.isUserFacing || isNotAnsweredSentence(failure.message)) {
    return noticeOf(failure.message, failure.details, actions, reportBug);
  }
  // A fallback of the shared helper's own says nothing the surface's sentence does not.
  const reason = failure.isReportable ? null : failure.message;
  return noticeOf(fallback, joinDetails([failure.details, reason]), actions, reportBug);
}
