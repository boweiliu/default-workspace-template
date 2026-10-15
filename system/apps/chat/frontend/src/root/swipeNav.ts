/**
 * The phone layout's swipe-between-chats gesture: a horizontal drag on the chat slot tracks the
 * next or previous row of the list (``rows.ts``'s display order) in live, carousel-style, so
 * switching chats on a phone does not require opening the drawer. Dragging past the newest end of
 * the list surfaces the "New chat" button the drawer already offers (``ChatRail``'s ``onNew``), in
 * place, instead of nothing happening.
 */

import type { ChatRow } from "./rows";

/** How far, and how straight, a touch has to travel before the drag engages (follows the finger)
 *  rather than reading as a tap or the transcript's own vertical scroll. Small on purpose: once
 *  engaged the frame is already following the finger, so a low bar is what makes that feel
 *  immediate rather than catching up partway through the drag. */
const ENGAGE_PX = 12;
const MIN_HORIZONTAL_RATIO = 1.5;

/** How much of the slot's width a drag has to cross before release commits it (switches chats, or
 *  shows the new-chat edge) rather than snapping back to where it started. */
export const COMMIT_FRACTION = 0.3;

/** How much a drag that can go nowhere (the resisted edge cases) moves the frame, relative to the
 *  raw finger movement -- the rest reads as resistance, as pulling against a boundary. */
export const RESIST_RATIO = 0.35;

export type SwipeDirection = "older" | "newer";

/** The drag's direction once it has gone far enough, straight enough, to engage; ``null`` while it
 *  still reads as a tap or a vertical scroll. */
export function swipeDirectionFromDelta(deltaX: number, deltaY: number): SwipeDirection | null {
  if (Math.abs(deltaX) < ENGAGE_PX) return null;
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

/** Whether `value` is an element node, without `instanceof Element`: the target passed in here always comes
 *  from a pointer/wheel event bound to a frame's own document (`framePool.ts`'s doc comment on why), so it is
 *  an instance of *that* document's own `Element`, a different constructor object than this module's global
 *  `Element` even though it is the identical class -- each browsing context gets its own built-ins, and
 *  `instanceof` compares constructor identity, not shape. `nodeType` is a plain number, not a constructor
 *  reference, so comparing it is the one check that reads the same regardless of which realm made the node
 *  (confirmed live: `instanceof` silently returned false for a real `<pre>` every time). */
function isElementNode(value: EventTarget | null): value is Element {
  return value !== null && "nodeType" in value && (value as Node).nodeType === Node.ELEMENT_NODE;
}

// How much `scrollHeight` is allowed to exceed `clientHeight` and still read as "no vertical overflow of its
// own" -- rounding from borders/padding, not real content, so a code block (which has none) still qualifies.
const VERTICAL_SLACK_PX = 2;

/** The nearest ancestor of `target` (inclusive) that scrolls horizontally on its own -- a long code block's
 *  `<pre>`, which keeps `overflow-x: auto` -- or `null` short of one. A touch landing on one of these is the
 *  chat page's own content to scroll, not ours to read as a swipe: CSS can't give it back once an ancestor
 *  restricts `touch-action` (confirmed live -- an explicit `pan-x pan-y` on the `<pre>` itself did not undo
 *  the page's own `pan-y`), so driving its `scrollLeft` by hand, from this same gesture, is what keeps the
 *  two working side by side instead of a dead zone with neither.
 *
 *  Also requires no vertical overflow of its own (confirmed live: the transcript's `overflow-y: auto`
 *  container matched otherwise). CSS Overflow's "visible is upgraded to auto" rule computes `overflow-x` as
 *  `auto` on ANY element whose `overflow-y` is set to something else, whether or not the author meant it to
 *  scroll horizontally at all -- a code block's `<pre>` only sets `overflow-x`, so this excludes the
 *  transcript's own scroller (overwhelmingly vertical) without excluding the thing this is actually for. */
export function findHorizontallyScrollableAncestor(target: EventTarget | null): HTMLElement | null {
  let element: Element | null = isElementNode(target) ? target : null;
  while (element !== null) {
    if (element.scrollWidth > element.clientWidth && element.scrollHeight <= element.clientHeight + VERTICAL_SLACK_PX) {
      const overflowX = getComputedStyle(element).overflowX;
      if (overflowX === "auto" || overflowX === "scroll") return element as HTMLElement;
    }
    element = element.parentElement;
  }
  return null;
}
