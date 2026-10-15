// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { findHorizontallyScrollableAncestor, swipeDirectionFromDelta, swipeTarget } from "./swipeNav";
import type { ChatRow } from "./rows";

function row(chatId: string): ChatRow {
  return { chatId, title: chatId, status: "idle", labels: {}, agentIds: [], lastActiveMs: null, isProvisional: false };
}

describe("swipeDirectionFromDelta", () => {
  it("reads a leftward drag past the threshold as moving to an older chat", () => {
    expect(swipeDirectionFromDelta(-80, 0)).toBe("older");
  });

  it("reads a rightward drag past the threshold as moving to a newer chat", () => {
    expect(swipeDirectionFromDelta(80, 0)).toBe("newer");
  });

  it("ignores a drag shorter than the engage threshold", () => {
    expect(swipeDirectionFromDelta(-8, 0)).toBeNull();
  });

  it("ignores a drag that is mostly vertical, even if long", () => {
    expect(swipeDirectionFromDelta(-70, -80)).toBeNull();
  });
});

describe("swipeTarget", () => {
  const rows = [row("agent-new"), row("agent-mid"), row("agent-old")];

  it("steps to the next-older row", () => {
    expect(swipeTarget(rows, "agent-new", "older")).toEqual({ kind: "select", chatId: "agent-mid" });
  });

  it("steps to the next-newer row", () => {
    expect(swipeTarget(rows, "agent-old", "newer")).toEqual({ kind: "select", chatId: "agent-mid" });
  });

  it("surfaces the new-chat edge when swiping older than the last row", () => {
    expect(swipeTarget(rows, "agent-old", "older")).toEqual({ kind: "new_chat_edge" });
  });

  it("does nothing swiping newer than the first row", () => {
    expect(swipeTarget(rows, "agent-new", "newer")).toEqual({ kind: "none" });
  });

  it("does nothing with no chat selected", () => {
    expect(swipeTarget(rows, null, "older")).toEqual({ kind: "none" });
  });

  it("does nothing when the selected chat is no longer in the list", () => {
    expect(swipeTarget(rows, "agent-gone", "older")).toEqual({ kind: "none" });
  });

  it("surfaces the new-chat edge from a single-row list", () => {
    expect(swipeTarget([row("agent-only")], "agent-only", "older")).toEqual({ kind: "new_chat_edge" });
  });
});

describe("findHorizontallyScrollableAncestor", () => {
  let iframe: HTMLIFrameElement | null = null;

  afterEach(() => {
    iframe?.remove();
    iframe = null;
  });

  function makeScrollable(doc: Document, overflowX: string): HTMLElement {
    const pre = doc.createElement("pre");
    pre.style.overflowX = overflowX;
    Object.defineProperty(pre, "scrollWidth", { value: 2000, configurable: true });
    Object.defineProperty(pre, "clientWidth", { value: 300, configurable: true });
    return pre;
  }

  it("finds a scrollable ancestor even across a realm boundary (an iframe's own Element constructor)", () => {
    iframe = document.createElement("iframe");
    document.body.appendChild(iframe);
    const innerDoc = iframe.contentDocument;
    if (innerDoc === null) throw new Error("iframe has no document");
    const pre = makeScrollable(innerDoc, "auto");
    const code = innerDoc.createElement("code");
    pre.appendChild(code);
    innerDoc.body.appendChild(pre);

    // `code` is an instance of the iframe's own `Element`, not this test file's -- the exact mismatch a
    // naive `instanceof Element` check (confirmed live, this module's history) silently fails against.
    expect(code instanceof Element).toBe(false);
    expect(findHorizontallyScrollableAncestor(code)).toBe(pre);
  });

  it("walks up from a non-scrollable descendant to find the row's scrollable ancestor", () => {
    const pre = makeScrollable(document, "auto");
    const code = document.createElement("code");
    pre.appendChild(code);
    expect(findHorizontallyScrollableAncestor(code)).toBe(pre);
  });

  it("returns null when nothing in the chain overflows", () => {
    const span = document.createElement("span");
    expect(findHorizontallyScrollableAncestor(span)).toBeNull();
  });

  it("returns null when overflow-x is neither auto nor scroll, even if wider than its box", () => {
    const pre = makeScrollable(document, "hidden");
    expect(findHorizontallyScrollableAncestor(pre)).toBeNull();
  });

  it("returns null for a non-element target", () => {
    expect(findHorizontallyScrollableAncestor(null)).toBeNull();
    expect(findHorizontallyScrollableAncestor(window)).toBeNull();
  });

  it("skips a vertically-scrolling container even though its own overflow-x also reads as auto", () => {
    // CSS Overflow's "visible is upgraded to auto" rule: setting only `overflow-y: auto` (the transcript's
    // own scroll container) computes `overflow-x` as `auto` too, with no author intent to scroll
    // horizontally at all -- confirmed live, this is the exact container that first tripped this up.
    const transcript = document.createElement("div");
    transcript.style.overflowX = "auto";
    Object.defineProperty(transcript, "scrollWidth", { value: 653, configurable: true });
    Object.defineProperty(transcript, "clientWidth", { value: 390, configurable: true });
    Object.defineProperty(transcript, "scrollHeight", { value: 9000, configurable: true });
    Object.defineProperty(transcript, "clientHeight", { value: 800, configurable: true });
    const message = document.createElement("div");
    transcript.appendChild(message);

    expect(findHorizontallyScrollableAncestor(message)).toBeNull();
  });
});
