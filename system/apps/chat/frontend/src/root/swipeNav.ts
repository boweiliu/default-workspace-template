/**
 * The phone layout's swipe-between-chats gesture: a horizontal drag on the chat slot moves to the
 * next or previous row of the list (``rows.ts``'s display order), so switching chats on a phone
 * does not require opening the drawer. Swiping past the newest end of the list surfaces the "New
 * chat" button the drawer already offers (``ChatRail``'s ``onNew``), in place, instead of nothing
 * happening.
 */

import type { ChatRow } from "./rows";

/** How far, and how straight, a touch has to travel to count as a swipe rather than a tap or a
 *  vertical scroll (the transcript itself scrolls vertically underneath this gesture). */
const MIN_SWIPE_PX = 60;
const MIN_HORIZONTAL_RATIO = 1.5;

export type SwipeDirection = "older" | "newer";

/** The direction a completed drag reads as, or ``null`` when it is a tap, a scroll, or a drag too
 *  short to count. */
export function swipeDirectionFromDelta(deltaX: number, deltaY: number): SwipeDirection | null {
  if (Math.abs(deltaX) < MIN_SWIPE_PX) return null;
  if (Math.abs(deltaX) < Math.abs(deltaY) * MIN_HORIZONTAL_RATIO) return null;
  // The list is newest-first (``rows.ts``): dragging left (deltaX < 0) steps toward it the same
  // way turning a page does, so it reads as moving to an older chat.
  return deltaX < 0 ? "older" : "newer";
}

export type SwipeOutcome =
  | { kind: "select"; chatId: string }
  | { kind: "new_chat_edge" }
  | { kind: "none" };

/** Where a swipe in ``direction`` lands, given the list's current display order and what is
 *  selected. Swiping older than the last row surfaces the new-chat edge; swiping newer than the
 *  first row, or with nothing selected or selected gone from the list, does nothing. */
export function swipeTarget(
  rows: readonly ChatRow[],
  selectedChatId: string | null,
  direction: SwipeDirection,
): SwipeOutcome {
  if (selectedChatId === null) return { kind: "none" };
  const index = rows.findIndex((row) => row.chatId === selectedChatId);
  if (index === -1) return { kind: "none" };
  const targetIndex = direction === "older" ? index + 1 : index - 1;
  if (targetIndex < 0) return { kind: "none" };
  if (targetIndex >= rows.length) return { kind: "new_chat_edge" };
  return { kind: "select", chatId: rows[targetIndex].chatId };
}
