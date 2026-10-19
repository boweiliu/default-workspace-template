/**
 * "Connecting to Opus 5.5 on Anthropic..." beside the model bar: a sent message is waiting for the agent
 * to come up, on the model and provider named as far as the chat knows them yet.
 *
 * Connecting is a sub-state of Sending (contract A1): the message already shows as sent, and
 * this says where the wait is. The backend reports it on the chat's snapshot
 * (``active_agent.is_connecting``). A chat still being created has no snapshot yet, and a message
 * sent to it waits for the create, so that wait reads the same way. A switching chat is left to
 * the handoff's own progress text.
 */

import m from "mithril";
import { activityDotClass } from "@imbue/workspace-ui/src/components/activityDot";
import { getChatById, getProvisionalChat } from "../models/Chats";
import { effectiveChoice } from "../models/ModelSettings";
import { getOutgoingMessages } from "../models/OutgoingMessages";
import { accountForAgent, accountForFirstSend } from "../models/Providers";

export function isChatConnecting(chatId: string): boolean {
  const chat = getChatById(chatId);
  if (chat !== undefined) {
    return chat.handoff === null && chat.active_agent.is_connecting;
  }
  const provisional = getProvisionalChat(chatId);
  return (
    provisional?.phase === "creating" && (provisional.held_sends.length > 0 || getOutgoingMessages(chatId).length > 0)
  );
}

/** What the indicator says: the model and the provider the message is waiting for, as far as they are known. */
export function connectingLabel(chatId: string): string {
  const chat = getChatById(chatId);
  const account =
    chat === undefined
      ? accountForFirstSend(getProvisionalChat(chatId)?.account_id)
      : accountForAgent(chat.active_agent.account_id ?? undefined);
  const model =
    chat === undefined ? null : (effectiveChoice(chatId, chat.active_agent.model_choice)?.matched?.label ?? null);
  const provider = account?.provider ?? null;
  if (model !== null && provider !== null) return `Connecting to ${model} on ${provider}…`;
  const target = model ?? provider;
  return target === null ? "Connecting…" : `Connecting to ${target}…`;
}

export function ConnectingIndicator(): m.Component<{ chatId: string }> {
  return {
    view(vnode) {
      if (!isChatConnecting(vnode.attrs.chatId)) return null;
      return m(
        "div",
        {
          class:
            "connecting-indicator flex min-w-0 items-center gap-1.5 px-1 type-helper whitespace-nowrap text-secondary",
          role: "status",
          "aria-live": "polite",
        },
        [
          m("span", { class: `connecting-indicator__dot ${activityDotClass("h-1.5 w-1.5", "warning")}` }),
          m("span", { class: "connecting-indicator__label truncate" }, connectingLabel(vnode.attrs.chatId)),
        ],
      );
    },
  };
}
