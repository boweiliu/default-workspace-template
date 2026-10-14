// @vitest-environment jsdom
/**
 * The chat list's verbs, failed: told in the root's styled notice with the server's text behind See details, never a
 * browser alert; a delete nothing answered keeps its row marked until the list says how it went.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.hoisted(() => {
  globalThis.requestAnimationFrame ??= ((cb: FrameRequestCallback): number =>
    setTimeout(() => cb(0), 0) as unknown as number) as typeof globalThis.requestAnimationFrame;
});

const verbs = vi.hoisted(() => ({
  stopChat: vi.fn(async (_chatId: string) => undefined),
  startChat: vi.fn(async (_chatId: string) => undefined),
  destroyChat: vi.fn(async (_chatId: string) => undefined),
  renameChat: vi.fn(async (_chatId: string, _title: string) => undefined),
}));
vi.mock("./verbs", () => verbs);

const chatsListeners = vi.hoisted(() => [] as (() => void)[]);
vi.mock("../models/Chats", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../models/Chats")>()),
  addChatsUpdatedListener: (listener: () => void) => chatsListeners.push(listener),
  removeChatsUpdatedListener: (listener: () => void) => {
    const index = chatsListeners.indexOf(listener);
    if (index >= 0) chatsListeners.splice(index, 1);
  },
}));

import m from "mithril";
import { HttpError } from "@imbue/workspace-ui/src/models/http";
import { isDeleting, rowMenuRows } from "./ChatRail";
import type { ChatRow } from "./rows";
import { RootNoticeView } from "./rootNotice";
import { chatRailAttrsFixture } from "./chatRailAttrsFixture";

const ROW: ChatRow = {
  chatId: "agent-1",
  title: "Plan the trip",
  status: "idle",
  labels: {},
  agentIds: ["agent-1"],
  lastActiveMs: null,
  isProvisional: false,
};

function select(key: string): void {
  const row = rowMenuRows(chatRailAttrsFixture({ rows: [ROW] }), ROW).find(
    (candidate) => candidate.kind === "action" && candidate.key === key,
  ) as { onSelect: () => void };
  row.onSelect();
}

async function rendered(): Promise<HTMLElement> {
  await new Promise((resolve) => setTimeout(resolve, 0));
  const root = document.createElement("div");
  m.render(root, m(RootNoticeView));
  return root;
}

function button(root: HTMLElement, label: string): HTMLElement | undefined {
  return Array.from(root.querySelectorAll("button")).find((b) => b.textContent === label);
}

describe("the chat list's failed verbs", () => {
  beforeEach(() => {
    verbs.stopChat.mockReset();
    verbs.destroyChat.mockReset();
    chatsListeners.length = 0;
    vi.stubGlobal("confirm", () => true);
    vi.stubGlobal("alert", () => {
      throw new Error("no browser alert");
    });
  });

  it("tells a refused Stop chat plainly, with the command output behind See details, and tries it again", async () => {
    verbs.stopChat.mockRejectedValue(
      new HttpError(500, "Failed to stop agent 'plan': mngr exited with code 1", "HTTP 500", false),
    );
    select("stop");
    const root = await rendered();

    expect(root.textContent).toContain(
      `Couldn't stop "Plan the trip". It's still running. Try again. If this persists, report a bug.`,
    );
    expect(root.querySelector(".see-details-text")?.textContent).toContain("mngr exited with code 1");
    expect(button(root, "Report a bug")).toBeDefined();
    button(root, "Try again")!.click();
    expect(verbs.stopChat).toHaveBeenCalledTimes(2);
  });

  it("says a chat that is gone is gone, with nothing to try again", async () => {
    verbs.stopChat.mockRejectedValue(
      new HttpError(
        404,
        "This chat is no longer here.",
        "HTTP 404\nChat 'agent-1' not found",
        false,
        true,
        false,
        "chat_gone",
      ),
    );
    select("stop");
    const root = await rendered();

    expect(root.textContent).toContain("This chat is no longer here.");
    expect(root.textContent).not.toContain("still running");
    expect(button(root, "Try again")).toBeUndefined();
  });

  it("says a delete nothing answered may have run, offers no retry, and keeps the row marked until the list updates", async () => {
    verbs.destroyChat.mockRejectedValue(
      new HttpError(502, "The workspace didn't answer.", "HTTP 502", false, false, true),
    );
    select("delete");
    const root = await rendered();

    expect(root.textContent).toContain(
      `The workspace didn't answer, so Imbue Studio can't tell whether "Plan the trip" was deleted.`,
    );
    expect(button(root, "Try again")).toBeUndefined();
    expect(isDeleting("agent-1")).toBe(true);

    for (const listener of [...chatsListeners]) listener();
    expect(isDeleting("agent-1")).toBe(false);
  });

  it("shows a half-done delete's own sentence and unmarks a refused one", async () => {
    verbs.destroyChat.mockRejectedValue(
      new HttpError(
        500,
        "This chat was only partly deleted: its agent is gone, but its conversation could not be removed. If the chat " +
          "comes back later, delete it again.",
        "HTTP 500",
        false,
        true,
      ),
    );
    select("delete");
    const root = await rendered();

    expect(root.textContent).toContain("This chat was only partly deleted");
    expect(isDeleting("agent-1")).toBe(false);
  });
});

describe("a message from outside a chat that the chat would not take", () => {
  it("says the message is in the chat's box when it was refused, with the refusal behind See details", async () => {
    const { describeIntakeApplyFailure } = await import("./rootNotice");
    const refused = new HttpError(400, "A pick names one of the chats that can take a message", "HTTP 400", false);
    const lines = describeIntakeApplyFailure(refused, true);
    expect(lines.body).toEqual(["Your message couldn't be sent to this chat. It's in the box below.", null]);
    expect(lines.details).toContain("A pick names one of the chats");
  });

  it("does not claim where the message went when nothing answered", async () => {
    const { describeIntakeApplyFailure } = await import("./rootNotice");
    const unanswered = new HttpError(504, "The workspace didn't answer.", "HTTP 504", false, false, true);
    expect(describeIntakeApplyFailure(unanswered, false).body).toEqual([
      "The workspace didn't answer, so Imbue Studio can't tell whether your message reached this chat.",
    ]);
  });
});
