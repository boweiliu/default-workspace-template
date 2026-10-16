import { beforeEach, describe, expect, it } from "vitest";

import {
  acceptPendingRename,
  dropPendingRename,
  settleAcceptedRenames,
  showPendingRename,
  titleWithPendingRename,
  withPendingTitles,
} from "./pendingRenames";
import type { ChatRow } from "./rows";

function row(chatId: string, title: string): ChatRow {
  return { chatId, title, status: "idle", labels: {}, agentIds: [chatId], lastActiveMs: null, isProvisional: false };
}

const titles = (rows: readonly ChatRow[]): string[] => rows.map((entry) => entry.title);

describe("pending renames", () => {
  beforeEach(() => {
    // Each test leaves its rename settled, so the next starts from the chat app's own names.
    for (const chatId of ["chat-a", "chat-b"]) {
      acceptPendingRename(chatId, "Plans");
      acceptPendingRename(chatId, "Trip");
    }
    settleAcceptedRenames();
  });

  it("shows the typed name at once, and only on the renamed chat", () => {
    showPendingRename("chat-a", "Plans", "Chat 1");

    expect(titles(withPendingTitles([row("chat-a", "Chat 1"), row("chat-b", "Chat 2")]))).toEqual(["Plans", "Chat 2"]);
    expect(titleWithPendingRename("chat-a", "Chat 1")).toBe("Plans");
  });

  it("keeps the typed name through chat lists that still carry the old one, until the rename is accepted", () => {
    showPendingRename("chat-a", "Plans", "Chat 1");
    settleAcceptedRenames();

    expect(titles(withPendingTitles([row("chat-a", "Chat 1")]))).toEqual(["Plans"]);

    acceptPendingRename("chat-a", "Plans");
    settleAcceptedRenames();

    expect(titles(withPendingTitles([row("chat-a", "Chat 1")]))).toEqual(["Chat 1"]);
  });

  it("gives way to the chat app's name as soon as it shows another", () => {
    showPendingRename("chat-a", "Plans", "Chat 1");

    // The chat app may store the name as it normalizes it.
    expect(titles(withPendingTitles([row("chat-a", "plans")]))).toEqual(["plans"]);
    expect(titles(withPendingTitles([row("chat-a", "Chat 1")]))).toEqual(["Chat 1"]);
  });

  it("brings the old name back when the rename is refused", () => {
    showPendingRename("chat-a", "Plans", "Chat 1");

    dropPendingRename("chat-a", "Plans");

    expect(titles(withPendingTitles([row("chat-a", "Chat 1")]))).toEqual(["Chat 1"]);
  });

  it("measures a second rename typed before the first landed against the chat app's name", () => {
    showPendingRename("chat-a", "Plans", "Chat 1");
    showPendingRename("chat-a", "Trip", "Plans");

    // The first refusal arrives late: the second rename's name stays.
    dropPendingRename("chat-a", "Plans");

    expect(titles(withPendingTitles([row("chat-a", "Chat 1")]))).toEqual(["Trip"]);
  });
});
