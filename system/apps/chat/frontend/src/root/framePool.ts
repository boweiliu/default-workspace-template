/**
 * The chat root's inner frames: one iframe of ``/<chat-id>`` per chat the root has shown this
 * session, the selected one visible and the rest hidden, so switching back is instant.
 *
 * Bounded: past ``MAX_HELD_FRAMES`` the frame shown longest ago is destroyed. Each page is handed
 * the shell's handshake to the root through the relay, as it loads. A hidden frame is
 * told ``hidden`` and a shown one ``shown`` through the page's embed API (the two documents
 * share an origin), which is what the page keys its presence reports on, so a chat held here
 * but not on screen counts as open-but-hidden, like a minimized window's page.
 */

import type { ShellHandshake } from "@imbue/workspace-ui/src/app_contract";
import { getBasePath } from "@imbue/workspace-ui/src/base-path";
import type { ChatPageEmbedApi } from "../embedApi";
import { handHandshakeDown } from "./relay";

export const MAX_HELD_FRAMES = 4;

/** The phone layout's swipe-between-chats gesture (swipeNav.ts): bound to each frame's own document, since a
 *  pointer inside the iframe never reaches a listener on the root's own page, same origin or not. Pointer
 *  Events (the same API ``ChatDrawer.ts`` drags with) read uniformly for a touch, a mouse, or a pen, so a
 *  mouse drag on a narrow desktop window exercises the identical path a phone's touch does -- no touch
 *  emulation needed to try it. */
export interface SwipeHandlers {
  onPointerDown: (event: PointerEvent) => void;
  onPointerMove: (event: PointerEvent) => void;
  onPointerUp: (event: PointerEvent) => void;
  onPointerCancel: (event: PointerEvent) => void;
  // A trackpad's two-finger swipe (macOS, under its default "natural scrolling") has no pointer down or up --
  // it only ever shows up as a stream of `wheel` events.
  onWheel: (event: WheelEvent) => void;
}

// The snap animation's duration and easing, for both a completed drag and an abandoned one.
const SNAP_TRANSITION = "transform 220ms cubic-bezier(0.22, 1, 0.36, 1)";
const SNAP_DURATION_MS = 220;

// What the shell grants an app page's frame (the PAGE_FRAME_SANDBOX of its live pages layer); a
// nested frame can hold no more than its parent, so this asks for the same.
const FRAME_SANDBOX =
  "allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-downloads allow-modals";
const FRAME_ALLOW = "clipboard-read; clipboard-write";

interface HeldFrame {
  frame: HTMLIFrameElement;
  lastShownAt: number;
  isLoaded: boolean;
}

export class InnerFramePool {
  private readonly held = new Map<string, HeldFrame>();
  private shownChatId: string | null = null;
  private handshake: ShellHandshake | null = null;
  private isRootShown = false;
  private isCompact = false;
  private swipeHandlers: SwipeHandlers | null = null;

  constructor(private readonly container: HTMLElement) {}

  /** Whether ``source`` is the window of one of this pool's frames. */
  isInnerWindow(source: MessageEventSource | null): boolean {
    if (source === null) return false;
    for (const { frame } of this.held.values()) {
      if (frame.contentWindow === source) return true;
    }
    return false;
  }

  /** The windows of this pool's frames. */
  innerWindows(): Window[] {
    const windows: Window[] = [];
    for (const { frame } of this.held.values()) {
      if (frame.contentWindow !== null) windows.push(frame.contentWindow);
    }
    return windows;
  }

  /** Show ``chatId`` (creating its frame on first sight), hiding whatever was shown; null shows nothing. Also
   *  the drag's clean slate: a frame a carousel drag left mid-transition always ends up either shown or hidden
   *  through ``endCarouselDrag``/``endResistDrag``, but this resets every frame's inline transform regardless,
   *  so a programmatic selection (the drawer, the New chat button) never inherits a stale one. */
  show(chatId: string | null): void {
    if (chatId !== null && !this.held.has(chatId)) this.create(chatId);
    const previous = this.shownChatId;
    this.shownChatId = chatId;
    if (previous !== null && previous !== chatId) this.tell(previous, "hidden");
    for (const [heldId, held] of this.held) {
      held.frame.style.transition = "";
      held.frame.style.transform = "";
      held.frame.style.pointerEvents = "";
      held.frame.hidden = heldId !== chatId;
    }
    if (chatId !== null) {
      const held = this.held.get(chatId);
      if (held !== undefined) held.lastShownAt = Date.now();
      if (this.isRootShown) this.tell(chatId, "shown");
    }
    this.evict();
  }

  /** Begin a live carousel drag: ``targetChatId``'s frame (created now if this is its first sight) appears
   *  beside the shown one, resting at ``restOffsetPx`` (its position before any drag delta is applied --
   *  positive is off-screen to the right, negative to the left) until ``updateCarouselDrag`` moves it. */
  beginCarouselDrag(targetChatId: string, restOffsetPx: number): void {
    if (this.shownChatId === null) return;
    if (!this.held.has(targetChatId)) this.create(targetChatId);
    const current = this.held.get(this.shownChatId);
    const target = this.held.get(targetChatId);
    if (current === undefined || target === undefined) return;
    current.frame.style.transition = "none";
    target.frame.style.transition = "none";
    target.frame.hidden = false;
    // The target is purely visual until the drag commits: both frames are full-size, absolutely-positioned
    // siblings (only a transform moves one of them), and a touch over the slot can land on either one's
    // document underneath that transform -- the current frame is the only one the gesture may drive.
    target.frame.style.pointerEvents = "none";
    current.frame.style.transform = "translateX(0px)";
    target.frame.style.transform = `translateX(${restOffsetPx}px)`;
  }

  /** Mid-drag: both frames follow the finger together, ``deltaPx`` applied to each from where
   *  ``beginCarouselDrag`` rested them. */
  updateCarouselDrag(targetChatId: string, deltaPx: number, restOffsetPx: number): void {
    if (this.shownChatId === null) return;
    const current = this.held.get(this.shownChatId);
    const target = this.held.get(targetChatId);
    if (current === undefined || target === undefined) return;
    current.frame.style.transform = `translateX(${deltaPx}px)`;
    target.frame.style.transform = `translateX(${restOffsetPx + deltaPx}px)`;
  }

  /** The drag's end. ``committed``: ``targetChatId`` finishes sliding fully into place and becomes the shown
   *  chat, the old one slides the rest of the way out. Not committed: both animate back to where
   *  ``beginCarouselDrag`` rested them, and the target's frame is left exactly as `show()` would have, as
   *  though the drag had never touched it. */
  endCarouselDrag(targetChatId: string, restOffsetPx: number, committed: boolean): void {
    const previousId = this.shownChatId;
    if (previousId === null) return;
    const current = this.held.get(previousId);
    const target = this.held.get(targetChatId);
    if (current === undefined || target === undefined) return;
    current.frame.style.transition = SNAP_TRANSITION;
    target.frame.style.transition = SNAP_TRANSITION;
    if (committed) {
      current.frame.style.transform = `translateX(${-restOffsetPx}px)`;
      target.frame.style.transform = "translateX(0px)";
      this.shownChatId = targetChatId;
      target.lastShownAt = Date.now();
    } else {
      current.frame.style.transform = "translateX(0px)";
      target.frame.style.transform = `translateX(${restOffsetPx}px)`;
    }
    window.setTimeout(() => {
      current.frame.style.transition = "";
      current.frame.style.transform = "";
      target.frame.style.transition = "";
      target.frame.style.transform = "";
      target.frame.style.pointerEvents = "";
      if (committed) {
        current.frame.hidden = true;
        this.tell(previousId, "hidden");
        if (this.isRootShown) this.tell(targetChatId, "shown");
        this.evict();
      } else {
        target.frame.hidden = true;
      }
    }, SNAP_DURATION_MS);
  }

  /** Begin a resisted drag with no frame to switch to (swiping past the newest or the oldest end of the
   *  list): the shown frame alone moves, scaled down, for the felt resistance of hitting an edge. */
  beginResistDrag(): void {
    if (this.shownChatId === null) return;
    const current = this.held.get(this.shownChatId);
    if (current === undefined) return;
    current.frame.style.transition = "none";
  }

  /** Mid-resisted-drag: ``scaledDeltaPx`` is the caller's already-dampened delta (``swipeNav.ts``'s
   *  resistance ratio applied to the raw finger movement). */
  updateResistDrag(scaledDeltaPx: number): void {
    if (this.shownChatId === null) return;
    const current = this.held.get(this.shownChatId);
    if (current === undefined) return;
    current.frame.style.transform = `translateX(${scaledDeltaPx}px)`;
  }

  /** The resisted drag's end: always snaps back, since there is nothing to commit to. */
  endResistDrag(): void {
    if (this.shownChatId === null) return;
    const current = this.held.get(this.shownChatId);
    if (current === undefined) return;
    current.frame.style.transition = SNAP_TRANSITION;
    current.frame.style.transform = "translateX(0px)";
    window.setTimeout(() => {
      current.frame.style.transition = "";
      current.frame.style.transform = "";
    }, SNAP_DURATION_MS);
  }

  /** The shell's word on whether the root is on screen, passed to the shown page. */
  setRootShown(isShown: boolean): void {
    this.isRootShown = isShown;
    if (this.shownChatId !== null) this.tell(this.shownChatId, isShown ? "shown" : "hidden");
  }

  /** Whether the root draws its phone layout, passed to every page (now and as each loads). */
  setCompact(isCompact: boolean): void {
    this.isCompact = isCompact;
    for (const chatId of this.held.keys()) this.api(chatId)?.setCompact(isCompact);
  }

  /** The handshake the shell gave the root, handed to every page (now and as each loads). */
  setHandshake(handshake: ShellHandshake): void {
    this.handshake = handshake;
    for (const chatId of this.held.keys()) this.introduce(chatId);
  }

  /** The swipe gesture's listeners, bound to every frame's document as it loads: a pointer lands in the
   *  iframe's own document, never the root's, so the root reaches in rather than listening on its own DOM. Set
   *  once, before any frame exists (``bootstrap``'s ``oncreate``), so there is nothing already held to rebind. */
  setSwipeHandlers(handlers: SwipeHandlers): void {
    this.swipeHandlers = handlers;
  }

  /** Drop a chat's frame (the chat was deleted). */
  destroy(chatId: string): void {
    const held = this.held.get(chatId);
    if (held === undefined) return;
    held.frame.remove();
    this.held.delete(chatId);
    if (this.shownChatId === chatId) this.shownChatId = null;
  }

  heldChatIds(): string[] {
    return [...this.held.keys()];
  }

  private create(chatId: string): void {
    const frame = document.createElement("iframe");
    frame.src = `${getBasePath()}/${encodeURIComponent(chatId)}`;
    frame.title = "Chat";
    frame.setAttribute("sandbox", FRAME_SANDBOX);
    frame.setAttribute("allow", FRAME_ALLOW);
    frame.className = "chat-root-frame absolute inset-0 h-full w-full border-0";
    frame.dataset.chatId = chatId;
    frame.hidden = true;
    const held: HeldFrame = { frame, lastShownAt: Date.now(), isLoaded: false };
    frame.addEventListener("load", () => {
      held.isLoaded = true;
      this.api(chatId)?.setCompact(this.isCompact);
      this.introduce(chatId);
      this.tell(chatId, this.isRootShown && this.shownChatId === chatId ? "shown" : "hidden");
      const innerDocument = frame.contentWindow?.document;
      if (innerDocument !== undefined && this.swipeHandlers !== null) {
        const { onPointerDown, onPointerMove, onPointerUp, onPointerCancel, onWheel } = this.swipeHandlers;
        innerDocument.addEventListener("pointerdown", onPointerDown);
        // Not passive: once a drag is engaged, onPointerMove/onWheel call preventDefault to hold off the
        // page's own vertical scroll (or, for wheel, the browser's swipe-to-navigate) for the rest of the
        // gesture.
        innerDocument.addEventListener("pointermove", onPointerMove, { passive: false });
        innerDocument.addEventListener("pointerup", onPointerUp);
        innerDocument.addEventListener("pointercancel", onPointerCancel);
        innerDocument.addEventListener("wheel", onWheel, { passive: false });
      }
    });
    this.held.set(chatId, held);
    this.container.appendChild(frame);
  }

  /** Hand ``text`` to the live composer of ``chatId``'s page; false when the page is not loaded yet (the caller
   *  then stores the draft where the page's composer reads it on mount). */
  draftInto(chatId: string, text: string): boolean {
    const api = this.api(chatId);
    if (api === null) return false;
    api.prependDraft(text);
    return true;
  }

  private api(chatId: string): ChatPageEmbedApi | null {
    const held = this.held.get(chatId);
    if (held === undefined || !held.isLoaded) return null;
    return held.frame.contentWindow?.chatPageEmbed ?? null;
  }

  private introduce(chatId: string): void {
    const held = this.held.get(chatId);
    const inner = held?.frame.contentWindow;
    if (this.handshake === null || held === undefined || !held.isLoaded || inner == null) return;
    handHandshakeDown(inner, this.handshake);
  }

  private tell(chatId: string, what: "shown" | "hidden"): void {
    const api = this.api(chatId);
    if (api === null) return;
    if (what === "shown") api.shown();
    else api.hidden();
  }

  private evict(): void {
    while (this.held.size > MAX_HELD_FRAMES) {
      let oldest: [string, HeldFrame] | null = null;
      for (const entry of this.held) {
        if (entry[0] === this.shownChatId) continue;
        if (oldest === null || entry[1].lastShownAt < oldest[1].lastShownAt) oldest = entry;
      }
      if (oldest === null) return;
      this.destroy(oldest[0]);
    }
  }
}
