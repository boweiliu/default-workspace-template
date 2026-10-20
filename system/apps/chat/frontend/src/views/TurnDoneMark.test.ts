// @vitest-environment jsdom
import m from "mithril";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../models/Chats", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../models/Chats")>()),
  getChatById: (id: string) => chats.get(id),
}));

import type { ActiveAgent, ChatSnapshot } from "../models/Chats";
import { chatSnapshotFixture, handoffStateFixture } from "../models/chatSnapshotFixture";
import { addOutgoing, clearOutgoing, getOutgoingMessages } from "../models/OutgoingMessages";
import type { TranscriptEvent } from "../models/Response";
import { TurnDoneMark, turnDoneLabel } from "./TurnDoneMark";

const CHAT_ID = "agent-1";
const chats = new Map<string, ChatSnapshot>();

function userMessage(timestamp: string): TranscriptEvent {
  return { type: "user_message", event_id: `u-${timestamp}`, timestamp, source: "test", role: "user", content: "hi" };
}

function reply(timestamp: string, isApiError = false): TranscriptEvent {
  return {
    type: "assistant_message",
    event_id: `a-${timestamp}`,
    timestamp,
    source: "test",
    model: "test-model",
    text: "done",
    tool_calls: [],
    stop_reason: "end_turn",
    usage: null,
    is_auth_error: false,
    is_api_error: isApiError,
    api_error_kind: null,
    is_provider_fault: false,
  };
}

const finishedTurn = [userMessage("2026-10-20T10:00:00Z"), reply("2026-10-20T10:00:14Z")];

function setChat(
  overrides: Partial<Omit<ChatSnapshot, "active_agent">> & { active_agent?: Partial<ActiveAgent> } = {},
): void {
  chats.set(
    CHAT_ID,
    chatSnapshotFixture(CHAT_ID, {
      ...overrides,
      active_agent: { activity_state: "IDLE", ...overrides.active_agent },
    }),
  );
}

describe("the done mark under the latest reply", () => {
  beforeEach(() => {
    vi.spyOn(m, "redraw").mockImplementation(() => undefined);
    setChat();
  });

  afterEach(() => {
    clearOutgoing(
      CHAT_ID,
      getOutgoingMessages(CHAT_ID).map((message) => message.id),
    );
    chats.clear();
    vi.restoreAllMocks();
  });

  it("says the turn is done, and how long the agent worked on it, once the chat is idle", () => {
    expect(turnDoneLabel(CHAT_ID, finishedTurn)).toBe("Worked for 14s");

    const root = document.createElement("div");
    m.render(root, m(TurnDoneMark, { chatId: CHAT_ID, events: finishedTurn }));
    expect(root.querySelector(".turn-done-mark .turn-done-mark__label")?.textContent).toBe("Worked for 14s");
    expect(root.querySelector(".turn-done-mark__check svg")).not.toBeNull();
  });

  it("says only Done for a turn that took under a second", () => {
    expect(turnDoneLabel(CHAT_ID, [userMessage("2026-10-20T10:00:00Z"), reply("2026-10-20T10:00:00.400Z")])).toBe(
      "Done",
    );
  });

  it.each([
    ["working", { status: "working" }],
    ["closing its turn", { status: "working", active_agent: { activity_state: "IDLE" } }],
    ["waiting on a background task", { status: "background" }],
    ["waiting on a permission answer", { status: "attention" }],
    ["stopped", { status: "stopped" }],
    ["switching to another harness", { handoff: handoffStateFixture() }],
    [
      "holding a queued message",
      { active_agent: { queued_messages: [{ queued_id: "q1", content: "next", timestamp: "" }] } },
    ],
    ["connecting", { active_agent: { is_connecting: true } }],
  ] as const)("shows nothing while the chat is %s", (_name, overrides) => {
    setChat(overrides as Parameters<typeof setChat>[0]);
    expect(turnDoneLabel(CHAT_ID, finishedTurn)).toBeNull();
  });

  it("gives way to a send of this page's on its way", () => {
    addOutgoing(CHAT_ID, "and one more thing");
    expect(turnDoneLabel(CHAT_ID, finishedTurn)).toBeNull();
  });

  it("leaves a turn that ended on a provider failure to that failure's notice", () => {
    expect(
      turnDoneLabel(CHAT_ID, [userMessage("2026-10-20T10:00:00Z"), reply("2026-10-20T10:00:03Z", true)]),
    ).toBeNull();
  });

  it("shows nothing for a turn the agent has not answered, or a chat with no transcript", () => {
    expect(turnDoneLabel(CHAT_ID, [userMessage("2026-10-20T10:00:00Z")])).toBeNull();
    expect(turnDoneLabel(CHAT_ID, [])).toBeNull();
  });
});
