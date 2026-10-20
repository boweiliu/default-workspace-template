/**
 * "Worked for 14s", with a check, under the latest reply once the agent has finished the turn: the
 * explicit end the status row above it hands over to, so a finished chat never reads as one that
 * might still be going. The number is the agent's own working time, so it says "worked for" rather
 * than claiming to be how long the user waited.
 *
 * It shows only when the backend reports the chat idle -- nothing in flight, nothing closing,
 * no background task to resume on, no permission to answer -- and this page has no send of its own
 * on the way. The duration is the transcript's own, from the message that opened the turn to the
 * last thing the agent recorded, so it matches the running timer and reads the same after a reload.
 */

import m from "mithril";
import { icon } from "@imbue/workspace-ui/src/components/icons";
import { getChatById } from "../models/Chats";
import { getOutgoingMessages } from "../models/OutgoingMessages";
import type { TranscriptEvent } from "../models/Response";
import { formatElapsed, latestTurnSpan } from "./turnTiming";

/** What the mark says for the transcript's latest turn, or null when it shows nothing. */
export function turnDoneLabel(chatId: string, events: readonly TranscriptEvent[]): string | null {
  const chat = getChatById(chatId);
  if (chat === undefined || chat.status !== "idle" || chat.handoff !== null) return null;
  const agent = chat.active_agent;
  if (agent.activity_state !== "IDLE" || agent.queued_messages.length > 0 || agent.is_connecting) return null;
  if (getOutgoingMessages(chatId).length > 0) return null;
  const last = events.length === 0 ? undefined : events[events.length - 1];
  // A turn that ended on a provider failure shows that failure's notice, not a finish.
  if (last === undefined || (last.type === "assistant_message" && (last.is_api_error || last.is_auth_error))) {
    return null;
  }
  const span = latestTurnSpan(events);
  if (span === null || !span.hasAgentWork) return null;
  const took = span.lastEventAt - span.startedAt;
  return took < 1000 ? "Done" : `Worked for ${formatElapsed(took)}`;
}

export function TurnDoneMark(): m.Component<{ chatId: string; events: TranscriptEvent[] }> {
  return {
    view(vnode) {
      const label = turnDoneLabel(vnode.attrs.chatId, vnode.attrs.events);
      if (label === null) return null;
      return m(
        "div",
        {
          class:
            "turn-done-mark mb-5 flex min-h-5 items-center gap-1.5 px-1 " +
            "text-(length:--font-size-helper) text-faint",
          role: "status",
        },
        [
          m(
            "span",
            { class: "turn-done-mark__check inline-flex shrink-0" },
            m.trust(icon("check", { size: 12, strokeWidth: 2.5 })),
          ),
          m("span", { class: "turn-done-mark__label" }, label),
        ],
      );
    },
  };
}
