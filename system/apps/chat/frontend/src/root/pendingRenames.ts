/**
 * The names the chat root shows for chats whose rename is on its way: the list, the phone header and the
 * shell's window title read the typed name the moment the field closes, while the chat app runs the rename
 * (an mngr rename, which takes seconds). The chat app's own name takes over once it reports one: when it
 * stops showing the old name, or with the first chat list after it accepted the rename (it reports the new
 * name before it answers). A refused rename is dropped here, so the old name comes back with the refusal.
 */

import type { ChatRow } from "./rows";

interface PendingRename {
  title: string;
  // The name the chat had when the rename was typed: once the chat app shows another, its name is the one.
  previousTitle: string;
  isAccepted: boolean;
}

const pendingByChatId = new Map<string, PendingRename>();

/** Show ``title`` for ``chatId``, shown as ``shownTitle`` now, until the chat app's own name for it takes over. */
export function showPendingRename(chatId: string, title: string, shownTitle: string): void {
  // A rename typed over one still on its way is measured against the name the chat app still has.
  const previousTitle = pendingByChatId.get(chatId)?.previousTitle ?? shownTitle;
  pendingByChatId.set(chatId, { title, previousTitle, isAccepted: false });
}

/** The chat app took the rename of ``chatId`` to ``title``: its next chat list carries the name. */
export function acceptPendingRename(chatId: string, title: string): void {
  const pending = pendingByChatId.get(chatId);
  if (pending !== undefined && pending.title === title) pending.isAccepted = true;
}

/** The chat app refused the rename of ``chatId`` to ``title``: the name it has stands. */
export function dropPendingRename(chatId: string, title: string): void {
  if (pendingByChatId.get(chatId)?.title === title) pendingByChatId.delete(chatId);
}

/** A chat list arrived: every accepted rename is in it, so the chat app's names take over for those. */
export function settleAcceptedRenames(): void {
  for (const [chatId, pending] of pendingByChatId) {
    if (pending.isAccepted) pendingByChatId.delete(chatId);
  }
}

/** ``rows`` with each pending rename's name in place of the old one, until the chat app shows another. */
export function withPendingTitles(rows: readonly ChatRow[]): ChatRow[] {
  return rows.map((row) => {
    const pending = pendingByChatId.get(row.chatId);
    if (pending === undefined) return row;
    if (row.title !== pending.previousTitle) {
      pendingByChatId.delete(row.chatId);
      return row;
    }
    return { ...row, title: pending.title };
  });
}

/** The name to show for ``chatId`` whose chat app name is ``title``. */
export function titleWithPendingRename(chatId: string, title: string): string {
  const pending = pendingByChatId.get(chatId);
  return pending !== undefined && pending.previousTitle === title ? pending.title : title;
}
