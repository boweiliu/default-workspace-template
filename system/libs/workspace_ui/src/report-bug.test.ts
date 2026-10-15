// @vitest-environment jsdom
//
// "Report a bug" against the real embed endpoint: the chrome's capabilities arrive as a message from the page's
// parent (in jsdom a top-level page is its own parent), and a press goes back to it as OPEN_HELP.

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { EMBEDDER_CAPABILITIES, resetEmbedEndpointForTesting, setEmbedderMessageHandler } from "./embed";
import { canReportBug, reportBugActions } from "./report-bug";

function capabilitiesArrive(payload: Record<string, unknown>): void {
  window.dispatchEvent(
    new MessageEvent("message", {
      data: { type: EMBEDDER_CAPABILITIES, canPopOut: false, ...payload },
      source: window,
    }),
  );
}

beforeEach(() => {
  // The page's own handler for the capabilities, as the shell registers one; it starts the endpoint listening.
  setEmbedderMessageHandler(EMBEDDER_CAPABILITIES, () => undefined);
});

afterEach(() => {
  resetEmbedEndpointForTesting();
});

describe("Report a bug", () => {
  it("is offered for a reportable failure only once the embedder says it opens its bug report", () => {
    expect(reportBugActions(true)).toEqual([]);
    capabilitiesArrive({});
    expect(canReportBug()).toBe(false);
    capabilitiesArrive({ opensHelp: true });
    expect(reportBugActions(true).map((action) => action.label)).toEqual(["Report a bug"]);
    expect(reportBugActions(false)).toEqual([]);
    capabilitiesArrive({ opensHelp: false });
    expect(reportBugActions(true)).toEqual([]);
  });

  it("asks the embedder to open its bug report when pressed", () => {
    capabilitiesArrive({ opensHelp: true });
    const posted: unknown[] = [];
    window.addEventListener("message", (event) => posted.push(event.data));
    reportBugActions(true)[0].run();
    return new Promise<void>((resolve) => setTimeout(resolve, 0)).then(() => {
      expect(posted).toContainEqual(expect.objectContaining({ type: "minds:open-help" }));
    });
  });
});
