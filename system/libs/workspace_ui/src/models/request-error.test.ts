import { describe, expect, it } from "vitest";

import { CHANGE_NOT_ANSWERED, READ_NOT_ANSWERED } from "./failure";
import { HttpError } from "./http";
import { REQUEST_FALLBACK_MESSAGE, describeRequestError, describeRequestFailure } from "./request-error";

// Every case here is a shape mithril actually rejects with; the point of the
// helper is that none of them can reach a user as a bare "null" or a status number.
describe("describeRequestFailure", () => {
  it("prefers the server's own detail, with the status behind the details", () => {
    const error = Object.assign(new Error("{}"), {
      code: 404,
      response: { detail: "Agent 'x' not found", kind: "chat_gone" },
    });
    expect(describeRequestFailure(error)).toEqual({
      message: "Agent 'x' not found",
      details: "HTTP 404",
      isReportable: false,
      isUserFacing: false,
      isNotAnswered: false,
      kind: "chat_gone",
    });
  });

  it("shows a sentence the server wrote for people in place of its detail", () => {
    const error = Object.assign(new Error("{}"), {
      code: 502,
      response: { detail: "chat answered the launch with 503", user_facing_message: "Chat is still starting." },
    });
    expect(describeRequestFailure(error)).toEqual({
      message: "Chat is still starting.",
      details: "HTTP 502\nchat answered the launch with 503",
      isReportable: false,
      isUserFacing: true,
      isNotAnswered: false,
      kind: null,
    });
  });

  it("offers a bug report for a server's sentence that asks for one", () => {
    const error = Object.assign(new Error("{}"), {
      code: 500,
      response: {
        detail: "Internal server error: boom",
        user_facing_message: "Something went wrong in this chat. Try again. If this persists, report a bug.",
      },
    });
    expect(describeRequestFailure(error).isReportable).toBe(true);
  });

  it("answers a status with no reason with the fallback, and keeps the status and raw text for the details", () => {
    const error = Object.assign(new Error('{"oops": true}'), { code: 500, response: { oops: true } });
    expect(describeRequestFailure(error)).toEqual({
      message: REQUEST_FALLBACK_MESSAGE,
      details: 'HTTP 500\n{"oops": true}',
      isReportable: true,
      isUserFacing: false,
      isNotAnswered: false,
      kind: null,
    });
  });

  it("never claims what a gateway status or a dropped connection did, and words a read apart from a change", () => {
    // A proxy's plain-text 503 under `responseType: "json"`: mithril cannot read the body, so it builds
    // `new Error(null)` -- message is the word "null". The proxy may have sent it after the request arrived.
    const gateway = Object.assign(new Error("Backend connection lost"), { code: 502, response: null });
    expect(describeRequestFailure(gateway).message).toBe(CHANGE_NOT_ANSWERED);
    expect(describeRequestFailure(gateway).details).toBe("HTTP 502\nBackend connection lost");
    expect(describeRequestFailure(gateway, "read").message).toBe(READ_NOT_ANSWERED);
    // Code 0 is mithril's "no HTTP response at all", and its own timeout is the same: nothing says whether the
    // request was carried out.
    const unanswered = Object.assign(new Error(String(null)), { code: 0, response: null });
    expect(describeRequestFailure(unanswered)).toEqual({
      message: CHANGE_NOT_ANSWERED,
      details: null,
      isReportable: false,
      isUserFacing: false,
      isNotAnswered: true,
      kind: null,
    });
    const timedOut = Object.assign(new Error("Request timed out"), { code: 0 });
    expect(describeRequestFailure(timedOut, "read").message).toBe(READ_NOT_ANSWERED);
    expect(describeRequestFailure(timedOut, "read").details).toBe("Request timed out");
  });

  it("passes an HttpError through as the REST helper read it", () => {
    const error = new HttpError(409, "the stored layout is newer", "HTTP 409", false);
    expect(describeRequestFailure(error)).toEqual({
      message: "the stored layout is newer",
      details: "HTTP 409",
      isReportable: false,
      isUserFacing: false,
      isNotAnswered: false,
      kind: null,
    });
  });

  it("keeps the message of an error a caller threw, which carries no status", () => {
    expect(describeRequestError(new Error("Chat creation returned no chat id"))).toBe(
      "Chat creation returned no chat id",
    );
  });

  it("never returns an empty sentence, whatever it is handed", () => {
    expect(describeRequestError(undefined)).toBe(REQUEST_FALLBACK_MESSAGE);
    expect(describeRequestError({})).toBe(REQUEST_FALLBACK_MESSAGE);
    expect(describeRequestError("   ")).toBe(REQUEST_FALLBACK_MESSAGE);
  });
});
