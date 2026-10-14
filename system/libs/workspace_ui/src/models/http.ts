/** What the workspace's REST routes answer, read the way the user needs it said. */

import {
  GATEWAY_STATUSES,
  asksForBugReport,
  fallbackSentence,
  joinDetails,
  nonEmptyString,
  notAnsweredSentence,
  type Failure,
  type RequestKind,
} from "./failure";

/** The fallback for a refusal that carries no reason. */
export const REST_FALLBACK_MESSAGE = fallbackSentence("Something went wrong in this workspace");

// How much of a body that is not a reason (an error page, a proxy's plain text) "See details" quotes.
const RAW_BODY_LIMIT = 2000;

/**
 * A refused or unanswered request to a REST route. ``message`` is what to show: a sentence the server wrote for
 * people (``user_facing_message``), else its ``detail`` (or ``error``), else one of the fallbacks. ``status`` is 0
 * when nothing answered.
 */
export class HttpError extends Error implements Failure {
  constructor(
    readonly status: number,
    message: string,
    readonly details: string | null,
    readonly isReportable: boolean,
    /** The server's sentence was written for people, so it stands on its own rather than after what failed. */
    readonly isUserFacing: boolean = false,
    /** Nothing answered (a gateway status, a dropped connection), so nothing says whether the request was carried
     *  out. */
    readonly isNotAnswered: boolean = false,
    /** The route's name for the case (its body's ``kind``), for a surface that offers different controls per case. */
    readonly kind: string | null = null,
  ) {
    super(message);
  }
}

interface ErrorBody {
  readonly user_facing_message?: unknown;
  readonly detail?: unknown;
  readonly error?: unknown;
  readonly details?: unknown;
  readonly kind?: unknown;
}

/** The failure a non-2xx ``response`` stands for. */
export async function readResponseFailure(response: Response, kind: RequestKind): Promise<HttpError> {
  const text = await response.text().catch(() => "");
  let body: ErrorBody = {};
  try {
    const parsed: unknown = JSON.parse(text);
    if (typeof parsed === "object" && parsed !== null) body = parsed as ErrorBody;
  } catch {
    // Not JSON (an error page, a proxy's plain text): quoted behind "See details" below.
  }
  const userFacing = nonEmptyString(body.user_facing_message);
  const reason = nonEmptyString(body.detail) ?? nonEmptyString(body.error);
  const details = joinDetails([
    `HTTP ${response.status}`,
    userFacing === null ? null : reason,
    nonEmptyString(body.details),
    userFacing === null && reason === null ? text.slice(0, RAW_BODY_LIMIT) : null,
  ]);
  const caseKind = nonEmptyString(body.kind);
  if (userFacing !== null) {
    return new HttpError(response.status, userFacing, details, asksForBugReport(userFacing), true, false, caseKind);
  }
  if (reason !== null) return new HttpError(response.status, reason, details, false, false, false, caseKind);
  if (GATEWAY_STATUSES.has(response.status)) {
    return new HttpError(response.status, notAnsweredSentence(kind), details, false, false, true);
  }
  return new HttpError(response.status, REST_FALLBACK_MESSAGE, details, true);
}

/** ``fetch`` that answers a request nothing answered (the connection refused or dropped) as an ``HttpError``. */
export async function fetchOrNotAnswered(url: string, init: RequestInit, kind: RequestKind): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (error) {
    throw new HttpError(0, notAnsweredSentence(kind), joinDetails([(error as Error).message]), false, false, true);
  }
}

/** GET ``url`` and answer the parsed JSON reply, throwing an ``HttpError`` on a refusal or no answer. */
export async function getJson<T>(url: string): Promise<T> {
  const response = await fetchOrNotAnswered(url, {}, "read");
  if (!response.ok) throw await readResponseFailure(response, "read");
  return (await response.json()) as T;
}

/** POST a JSON body and answer the parsed JSON reply, throwing an ``HttpError`` on a refusal or no answer. */
export async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetchOrNotAnswered(
    url,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    "change",
  );
  if (!response.ok) throw await readResponseFailure(response, "change");
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
