import {
  GATEWAY_STATUSES,
  fallbackSentence,
  joinDetails,
  notAnsweredSentence,
  type Failure,
  type RequestKind,
} from "./failure";
import { HttpError } from "./http";

/**
 * Messages that carry no information, in the spellings a stringified body takes.
 *
 * Mithril builds its rejection as `new Error(body)`, and `Error` stringifies
 * whatever it is handed -- so a body it could not read arrives as the *word*
 * "null", not as an absent message. (With `responseType: "json"` and a
 * non-JSON body, `xhr.response` is null and reading `xhr.responseText` throws,
 * which is exactly a proxy's plain-text 503.) An emptiness check alone lets
 * that through. A parsed object body lands here as "[object Object]" the same
 * way. ("undefined" is
 * unreachable from mithril itself -- `new Error(undefined).message` is "" --
 * and is listed only so any other producer of this shape is covered too.)
 */
const UNINFORMATIVE_MESSAGES: ReadonlySet<string> = new Set(["null", "undefined", "[object Object]"]);

/** The fallback for a failed request that carries no reason. */
export const REQUEST_FALLBACK_MESSAGE = fallbackSentence("The workspace couldn't do that");

/** A failure as ``describeRequestFailure`` reads it: the server's own sentence, when it gave one, is ``message``. */
export interface RequestFailure extends Failure {
  /** The server's sentence was written for people, so it stands on its own rather than after what failed. */
  readonly isUserFacing: boolean;
}

function informativeMessage(value: unknown): string | null {
  const message = typeof value === "string" ? value.trim() : "";
  return message !== "" && !UNINFORMATIVE_MESSAGES.has(message) ? message : null;
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}

/**
 * Read a failed request -- a mithril `m.request` rejection, an ``HttpError``, or an error a caller threw -- as what to
 * show and what goes behind "See details".
 *
 * A mithril rejection carries (when available) the parsed response body, the HTTP status as `code`, and a `message`
 * that is the raw body text. The server's own `detail` is shown as written; a status with no reason reads as a
 * fallback of ours, with the status and any raw text behind the details.
 */
export function describeRequestFailure(error: unknown, kind: RequestKind = "change"): RequestFailure {
  if (error instanceof HttpError) {
    return {
      message: error.message,
      details: error.details,
      isReportable: error.isReportable,
      isUserFacing: error.isUserFacing,
    };
  }
  const fallback: RequestFailure = {
    message: REQUEST_FALLBACK_MESSAGE,
    details: null,
    isReportable: true,
    isUserFacing: false,
  };
  if (error === null || error === undefined) return fallback;
  if (typeof error === "string") {
    const text = error.trim();
    return text === "" ? fallback : { ...fallback, message: text, isReportable: false };
  }
  const err = error as {
    response?: { user_facing_message?: unknown; detail?: unknown; error?: unknown } | null;
    message?: unknown;
    code?: unknown;
  };
  const message = informativeMessage(err.message);

  // Not a request's rejection: an error a caller threw, whose message is its own.
  if (typeof err.code !== "number") {
    return message === null ? fallback : { ...fallback, message, isReportable: false };
  }

  const userFacing = nonEmptyString(err.response?.user_facing_message);
  const reason = nonEmptyString(err.response?.detail) ?? nonEmptyString(err.response?.error);
  const status = err.code === 0 ? null : `HTTP ${err.code}`;
  if (userFacing !== null) {
    return { message: userFacing, details: joinDetails([status, reason]), isReportable: false, isUserFacing: true };
  }
  if (reason !== null) {
    return { message: reason, details: status, isReportable: false, isUserFacing: false };
  }
  // The body's raw text (mithril's `message`), behind the details. Code 0 is mithril's "no HTTP response at all": a
  // connection refused or dropped, or its own timeout, so nothing says whether the request was carried out.
  const details = joinDetails([status, message]);
  if (err.code === 0 || GATEWAY_STATUSES.has(err.code)) {
    return { message: notAnsweredSentence(kind), details, isReportable: false, isUserFacing: false };
  }
  return { ...fallback, details };
}

/** The sentence ``describeRequestFailure`` shows for ``error``; always non-empty. */
export function describeRequestError(error: unknown, kind: RequestKind = "change"): string {
  return describeRequestFailure(error, kind).message;
}

/**
 * mngr's classification of a failed send, when it supplied one.
 *
 * The reason a send failed is written for a person and varies per harness, so it cannot be used
 * to decide whether trying again could possibly help. This is the machine-readable half. mngr
 * names the situation and stops there -- it does not know what a button is -- so the mapping from
 * a kind to what the user is offered lives here, in the workspace.
 *
 * Anything unrecognised (an older backend, a kind added later) reads as "unknown", for which
 * callers offer nothing kind-specific.
 */
export type SendFailureKind = "input_blocked" | "not_ready" | "agent_unreachable" | "unknown";

const KNOWN_SEND_FAILURE_KINDS: ReadonlySet<string> = new Set(["input_blocked", "not_ready", "agent_unreachable"]);

export function describeRequestErrorKind(error: unknown): SendFailureKind {
  if (error === null || typeof error !== "object") {
    return "unknown";
  }
  const kind = (error as { response?: { kind?: unknown } | null }).response?.kind;
  return typeof kind === "string" && KNOWN_SEND_FAILURE_KINDS.has(kind) ? (kind as SendFailureKind) : "unknown";
}
