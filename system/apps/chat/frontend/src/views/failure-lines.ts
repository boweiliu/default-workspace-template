/**
 * What the chat page says about a failed request: the sentences on screen and what goes behind "See details". Each
 * surface names what failed; the server's own sentence (its ``user_facing_message``) is shown as written when it
 * wrote one, a request nothing answered gets the surface's can't-tell sentence, and anything else gets the fallback
 * "<what failed>. Try again. If this persists, report a bug." with the server's text behind the details.
 */

import { fallbackSentence, joinDetails, notAnsweredSentence } from "@imbue/workspace-ui/src/models/failure";
import type { RequestKind } from "@imbue/workspace-ui/src/models/failure";
import { describeRequestFailure } from "@imbue/workspace-ui/src/models/request-error";
import type { RequestFailure } from "@imbue/workspace-ui/src/models/request-error";

export interface FailureLines {
  /** The paragraphs on screen, in order; empty entries are dropped. */
  readonly body: readonly (string | null)[];
  /** What goes behind "See details"; null when there is nothing beyond the body. */
  readonly details: string | null;
  /** The body asks for a bug report, so the surface offers "Report a bug". */
  readonly isReportable: boolean;
}

/** Everything a failure carries that is not already the visible sentence. */
export function detailsBehind(failure: RequestFailure): string | null {
  return failure.isUserFacing || failure.isNotAnswered || failure.isReportable
    ? failure.details
    : joinDetails([failure.message, failure.details]);
}

/**
 * ``error`` told the plain way: the server's own sentence when it wrote one, ``notAnswered`` when nothing answered,
 * else ``whatFailed`` followed by the fallback ending, with the server's text behind the details.
 */
export function plainFailureLines(
  error: unknown,
  whatFailed: string,
  options: { requestKind?: RequestKind; notAnswered?: string } = {},
): FailureLines {
  const requestKind = options.requestKind ?? "change";
  const failure = describeRequestFailure(error, requestKind);
  if (failure.isNotAnswered) {
    return {
      body: [options.notAnswered ?? notAnsweredSentence(requestKind)],
      details: failure.details,
      isReportable: false,
    };
  }
  if (failure.isUserFacing) {
    return { body: [failure.message], details: failure.details, isReportable: failure.isReportable };
  }
  return { body: [fallbackSentence(whatFailed)], details: detailsBehind(failure), isReportable: true };
}

/** The one-paragraph sentence of ``plainFailureLines``, for a surface with room for a single line. */
export function plainFailureSentence(lines: FailureLines): string {
  return lines.body.filter((line): line is string => line !== null && line !== "").join(" ");
}
