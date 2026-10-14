import { describe, expect, it } from "vitest";
import { swipeDirectionFromDelta, swipeTarget } from "./swipeNav";
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
