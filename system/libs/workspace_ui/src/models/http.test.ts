import { afterEach, describe, expect, it, vi } from "vitest";
import { CHANGE_NOT_ANSWERED, READ_NOT_ANSWERED } from "./failure";
import { HttpError, REST_FALLBACK_MESSAGE, getJson, postJson } from "./http";

function answering(status: number, body: unknown, contentType = "application/json"): void {
  const text = body === undefined ? null : typeof body === "string" ? body : JSON.stringify(body);
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(text, { status, headers: { "Content-Type": contentType } })),
  );
}

async function failureOf(request: Promise<unknown>): Promise<HttpError> {
  const failure = await request.catch((error: unknown) => error);
  expect(failure).toBeInstanceOf(HttpError);
  return failure as HttpError;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("postJson", () => {
  it("answers the parsed reply, and nothing for a 204", async () => {
    answering(200, { updated_at: "t1" });
    expect(await postJson<{ updated_at: string }>("/api/x", { a: 1 })).toEqual({ updated_at: "t1" });
    answering(204, undefined);
    expect(await postJson<void>("/api/x", {})).toBeUndefined();
  });

  it("throws the server's detail with the status a caller can tell refusals apart by", async () => {
    answering(409, { detail: "the stored layout is newer" });
    const failure = await failureOf(postJson("/api/x", {}));
    expect(failure).toMatchObject({ status: 409, message: "the stored layout is newer", details: "HTTP 409" });
    expect(failure.isUserFacing).toBe(false);
  });

  it("shows a sentence written for people on its own, with the developer's detail behind the details", async () => {
    const couldNotOpen = "Chat couldn't open that. Try again. If this persists, report a bug.";
    answering(502, { detail: "chat answered the launch with 500: boom", user_facing_message: couldNotOpen });
    const failure = await failureOf(postJson("/api/x", {}));
    expect(failure).toMatchObject({
      message: couldNotOpen,
      details: "HTTP 502\nchat answered the launch with 500: boom",
      isUserFacing: true,
      // It asks for a bug report, so the surface offers the button.
      isReportable: true,
    });
  });

  it("keeps the answer's own fields for a caller that words the refusal itself", async () => {
    answering(400, {
      detail: "No registered app named 'files'",
      user_facing_message: "Gone.",
      kind: "app_unavailable",
    });
    const failure = await failureOf(postJson("/api/x", {}));
    expect(failure.body?.kind).toBe("app_unavailable");
    answering(500, "<html>Internal Server Error</html>", "text/html");
    expect((await failureOf(postJson("/api/x", {}))).body).toBeNull();
  });

  it("answers a refusal with no reason with the fallback, the body behind the details", async () => {
    answering(500, "<html>Internal Server Error</html>", "text/html");
    const failure = await failureOf(postJson("/api/x", {}));
    expect(failure).toMatchObject({
      status: 500,
      message: REST_FALLBACK_MESSAGE,
      details: "HTTP 500\n<html>Internal Server Error</html>",
      isReportable: true,
    });
  });

  it("never says a change was not made when a gateway answered or nothing did", async () => {
    answering(504, "Backend timed out", "text/plain");
    const gateway = await failureOf(postJson("/api/x", {}));
    expect(gateway).toMatchObject({ message: CHANGE_NOT_ANSWERED, details: "HTTP 504\nBackend timed out" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const unanswered = await failureOf(postJson("/api/x", {}));
    expect(unanswered).toMatchObject({ status: 0, message: CHANGE_NOT_ANSWERED, details: "Failed to fetch" });
  });
});

describe("getJson", () => {
  it("words a read nothing answered as a read", async () => {
    answering(503, undefined);
    expect(await failureOf(getJson("/api/x"))).toMatchObject({ message: READ_NOT_ANSWERED, details: "HTTP 503" });
  });
});
