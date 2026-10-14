/**
 * The chat root: the chat list beside an inner frame of the selected chat, served by the chat
 * app at ``/`` (``/?chat=<id>`` selects). See docs/system/blueprint/desktop-interface/plan-desktop-interface.md
 * section 9.1 and docs/system/blueprint/post-launch-paths/plan-post-launch-paths.md section 3.6.
 *
 * The root owns the shell connection: it reports ``/?chat=<id>`` and the selected chat's
 * title as its location, handles ``shell:navigate`` by changing the selection, applies the
 * pending intake an ``intake=<token>`` in its URL names (a draft into a composer, a choice of
 * chat through the picker, or a first message that launches a chat through the provider
 * chooser) exactly once and then reports the selection alone, and drives its inner pages
 * directly (they share an origin) with the shell's handshake and its shown and hidden states,
 * so each page's presence reports key on the chat it shows. The inner pages' own ``minds:``,
 * ``shell:focused``, and sub-agent ``shell:open`` messages go up through ``relay.ts``; a page
 * asking for a sibling chat is answered here, by selecting it.
 */

import m from "mithril";
import "../style.css";
import { connectToShell } from "@imbue/workspace-ui/src/app_contract";
import type { ShellConnection, ShellHandshake } from "@imbue/workspace-ui/src/app_contract";
import { createContextMenuOpener } from "@imbue/workspace-ui/src/components/contextMenuOpener";
import { installElementContextMenu } from "@imbue/workspace-ui/src/context_menu";
import { installCursorHidingWhileTyping } from "@imbue/workspace-ui/src/hideCursorWhileTyping";
import { scopeOfHandshake } from "@imbue/workspace-ui/src/element_reference";
import { getBasePath } from "@imbue/workspace-ui/src/base-path";
import { adoptClientIdentity } from "@imbue/workspace-ui/src/models/ClientIdentity";
import { ReconnectBackoff } from "@imbue/workspace-ui/src/models/backoff";
import {
  PendingIntakeGoneError,
  addChatsUpdatedListener,
  applyPendingIntake,
  awaitingChatForEmptyList,
  createChat,
  discardPendingIntake,
  fetchPendingIntake,
  getChatById,
  getChats,
  getProvisionalChats,
  hasReceivedChatList,
  initChats,
  launchChat,
  removeChatsUpdatedListener,
} from "../models/Chats";
import type { AppliedIntake, PendingIntake } from "../models/Chats";
import {
  accountForFirstSend,
  closeProviderChooser,
  getSelectedAccount,
  isProviderChooserOpen,
  loadAccountsWithRetry,
  openProviderChooser,
  whenAccountsReadyToChoose,
} from "../models/Providers";
import { ProviderChooserModal } from "../views/ProviderChooserModal";
import { COMPACT_MEDIA_QUERY } from "../compactLayout";
import { plusGlyph } from "../glyphs";
import { ChatDrawer } from "./ChatDrawer";
import { ChatHeader } from "./ChatHeader";
import { ChatRail } from "./ChatRail";
import type { ChatRailAttrs } from "./ChatRail";
import { SendPicker } from "./SendPicker";
import { initChatUnread, markRead, noteStatuses } from "./chatUnread";
import { InnerFramePool } from "./framePool";
import { startInnerFrameRelay } from "./relay";
import { groupedRows, rowsFromSnapshots } from "./rows";
import type { ChatRow } from "./rows";
import { intakeTokenFromSearch, rootPathFor, selectionFromSearch, slotFill } from "./selection";
import type { SlotFill } from "./selection";
import { COMMIT_FRACTION, RESIST_RATIO, swipeDirectionFromDelta, swipeTarget } from "./swipeNav";
import { prependToComposer } from "../views/MessageInput";

const ROOT_TITLE = "Chats";

let selectedChatId: string | null = null;
let connection: ShellConnection | null = null;
let handshake: ShellHandshake | null = null;
let isRootShown = true;
let pool: InnerFramePool | null = null;
// The intake the root's URL named and has not yet applied or given up (waiting for the chats, fetched, offered
// through the picker); null otherwise. While one is pending the shell holds the window at the token path it put it
// at, and the root reports no other location, so a reload or another client finds the token too.
let pendingToken: string | null = null;
// A held intake whose chat the user has to pick, while its picker is open; null otherwise.
let pendingPick: { token: string; intake: PendingIntake } | null = null;
// The chats started from this root: on top of the list until their first message.
const startedHere = new Set<string>();
// The chats this root created that no push has named yet. The socket's connect-time replay can land after the create
// returned, with a chat list from before it, and the chat's provisional record only follows that replay.
const awaitingListing = new Set<string>();
// The phone layout (compactLayout.ts): a header over the chat, and the list in a drawer over it.
const compactQuery = window.matchMedia(COMPACT_MEDIA_QUERY);
// Whether the phone layout's drawer is open. It opens whenever nothing is selected, and closes when a chat is picked.
let isDrawerOpen = false;
// The phone layout's swipe-between-chats gesture (swipeNav.ts): the pointer (a touch, a mouse, or a pen --
// `framePool.ts` binds these as Pointer Events) currently driving one, and its start point for the gesture's
// life; a second pointer going down mid-gesture is ignored rather than disrupting the one already tracked.
// Also whether a drag past the newest chat left the "New chat" edge showing.
let activeSwipePointerId: number | null = null;
let swipeStartPoint: { x: number; y: number } | null = null;
let isAtNewChatEdge = false;
// What the current gesture has engaged into, once it has gone far enough to read as a swipe rather than a tap
// or a vertical scroll (``null`` before that, and again once the gesture ends). ``restOffsetPx`` is where
// ``targetChatId``'s frame rests before any drag delta, for ``framePool.ts``'s carousel; the resisted cases
// (nothing to switch to) carry none, since only the shown frame itself moves, scaled down.
type EngagedDrag =
  | { kind: "select"; targetChatId: string; restOffsetPx: number }
  | { kind: "resist"; isAtNewChatEdge: boolean };
let engagedDrag: EngagedDrag | null = null;

function selectedTitle(): string {
  if (selectedChatId === null) return "";
  return getChatById(selectedChatId)?.title ?? "";
}

interface ReportedLocation {
  path: string;
  title: string;
}

// The last location told to the shell: every chat list push re-derives it, and only a change goes up.
let reportedLocation: ReportedLocation | null = null;

function reportLocation(): void {
  if (pendingToken !== null) return;
  const path = rootPathFor(selectedChatId);
  const title = selectedTitle();
  if (reportedLocation !== null && reportedLocation.path === path && reportedLocation.title === title) return;
  reportedLocation = { path, title };
  document.title = title || ROOT_TITLE;
  connection?.location(path, title);
}

// Whether a chat for the empty list is being asked for, so the list asks once.
let isOpeningChatForEmptyList = false;
// Paces asking again after a failure: the app refuses until it has read its agent list, and a list that is still
// empty after that brings no push to ask again on (an unchanged list is not passed on).
const emptyListChatBackoff = new ReconnectBackoff();

/** The rail's rows in display order, most recent first. */
function railRows(): ChatRow[] {
  return groupedRows(rowsFromSnapshots(getChats(), getProvisionalChats()), startedHere);
}

function slotFillFor(chatId: string | null): SlotFill {
  return slotFill({
    selectedChatId: chatId,
    chatIds: railRows().map((row) => row.chatId),
    isChatListKnown: hasReceivedChatList(),
    isChoosing: pendingToken !== null || pendingPick !== null,
    isCompact: compactQuery.matches,
    isShown: isRootShown,
  });
}

/** Show ``chatId``: the URL, the frame, the shell's location, and the unread mark follow. Asked to show nothing, the
 *  root shows the most recent chat instead, or with no chats one awaiting its first send (``slotFill``). */
function select(chatId: string | null): void {
  const fill = slotFillFor(chatId);
  const shown = fill.kind === "select" ? fill.chatId : chatId;
  selectedChatId = shown;
  isDrawerOpen = shown === null;
  isAtNewChatEdge = false;
  history.replaceState(null, "", `${getBasePath()}${rootPathFor(shown)}`);
  pool?.show(shown);
  if (shown !== null && isRootShown) markRead(shown);
  reportLocation();
  m.redraw();
  if (fill.kind === "open_new") openChatForEmptyList();
}

/** Fill an empty slot now that something it depends on changed (the chat list arrived, the root came on screen, the
 *  layout left the phone width). */
function fillSlot(): void {
  if (selectedChatId === null && slotFillFor(null).kind !== "keep") select(null);
}

function openChatForEmptyList(): void {
  if (isOpeningChatForEmptyList) return;
  isOpeningChatForEmptyList = true;
  awaitingChatForEmptyList()
    .then((chatId) => {
      emptyListChatBackoff.reset();
      awaitingListing.add(chatId);
      if (selectedChatId === null) select(chatId);
    })
    .catch((error: unknown) => {
      console.warn("[chat-root] could not open a chat for the empty list; asking again", error);
      setTimeout(fillSlot, emptyListChatBackoff.nextDelay());
    })
    .finally(() => {
      isOpeningChatForEmptyList = false;
    });
}

async function createAndSelect(accountId: string): Promise<void> {
  try {
    const created = await createChat("", accountId);
    startedHere.add(created.chatId);
    awaitingListing.add(created.chatId);
    select(created.chatId);
  } catch (error) {
    alert(`Failed to create chat: ${(error as Error).message}`);
  }
}

/** The New chat button: a chat on the selected account, or after a sign-in when nothing is signed in. */
async function startNewChat(): Promise<void> {
  await whenAccountsReadyToChoose();
  const account = getSelectedAccount();
  if (account !== null) {
    await createAndSelect(account.id);
    return;
  }
  openProviderChooser({ onSignedIn: (signedInAccountId) => void createAndSelect(signedInAccountId) });
}

/** The chat slot's width, the carousel's unit: a frame rests one slot-width off-screen before a drag reaches
 *  it, and a drag has to cross `COMMIT_FRACTION` of it to commit. Read fresh each gesture rather than cached,
 *  since a rotation or a resize between gestures is the normal case on a phone. */
function slotWidthPx(): number {
  return document.querySelector<HTMLElement>(".chat-root-slot")?.clientWidth ?? window.innerWidth;
}

/** The phone layout's swipe gesture: a pointer inside a frame never reaches a listener on the root's own page
 *  (`framePool.ts` binds these to each frame's document instead), so these ignore the desktop layout
 *  themselves rather than relying on being unbound there. A primary-button press (or a touch or pen contact)
 *  starts it; a second one going down mid-gesture is ignored. Nothing else happens yet -- `onFramePointerMove`
 *  engages the drag once it has gone far enough to tell a swipe from a tap or the transcript's own vertical
 *  scroll. Pointer Events read a mouse the same way as a touch, so a drag on a narrow desktop window exercises
 *  this identically to a phone -- no touch emulation needed to try it. */
function onFramePointerDown(event: PointerEvent): void {
  if (!compactQuery.matches || activeSwipePointerId !== null) return;
  if (event.pointerType === "mouse" && event.button !== 0) return;
  activeSwipePointerId = event.pointerId;
  swipeStartPoint = { x: event.screenX, y: event.screenY };
  engagedDrag = null;
}

/** Each move past engagement follows the pointer 1:1 (the carousel case) or at `RESIST_RATIO` (the resisted
 *  edge cases), live, through `framePool.ts` -- this is the carousel itself, not just its trigger. Engaging
 *  also claims the gesture from the page's own vertical scroll (`preventDefault`), since a drag that has
 *  already committed to a direction reading as a scroll too, mid-swipe, would fight the frame underneath it.
 *
 *  Reads `screenX`/`screenY` (position on the physical screen), not `clientX`/`clientY`: once a frame starts
 *  moving under `updateCarouselDrag`, a pointer's `clientX` inside that same frame is computed against its own
 *  now-shifting rendered position and comes back corrupted (confirmed live: it alternates between two readings
 *  a constant offset apart, one per rendering pass, as the frame's own transform changes). `screenX` is defined
 *  relative to the physical screen, which no page-level transform can move, so a plain delta from the gesture's
 *  start stays correct for the drag's whole duration. */
function onFramePointerMove(event: PointerEvent): void {
  if (event.pointerId !== activeSwipePointerId) return;
  const start = swipeStartPoint;
  if (start === null) return;
  const deltaX = event.screenX - start.x;
  if (engagedDrag === null) {
    const direction = swipeDirectionFromDelta(deltaX, event.screenY - start.y);
    if (direction === null) return;
    const outcome = swipeTarget(railRows(), selectedChatId, direction);
    if (outcome.kind === "select") {
      const restOffsetPx = direction === "older" ? slotWidthPx() : -slotWidthPx();
      pool?.beginCarouselDrag(outcome.chatId, restOffsetPx);
      engagedDrag = { kind: "select", targetChatId: outcome.chatId, restOffsetPx };
    } else {
      pool?.beginResistDrag();
      engagedDrag = { kind: "resist", isAtNewChatEdge: outcome.kind === "new_chat_edge" };
    }
  }
  if (event.cancelable) event.preventDefault();
  if (engagedDrag.kind === "select") {
    pool?.updateCarouselDrag(engagedDrag.targetChatId, deltaX, engagedDrag.restOffsetPx);
  } else {
    pool?.updateResistDrag(deltaX * RESIST_RATIO);
  }
}

/** The drag's end: past `COMMIT_FRACTION` of the slot's width, it switches chats or, past the newest one,
 *  leaves the "New chat" button showing in its place; short of it, the carousel snaps back to where it
 *  started. A gesture that never engaged (a tap, or a scroll `onFramePointerMove` left to the page) has
 *  nothing to settle. */
function onFramePointerUp(event: PointerEvent): void {
  if (event.pointerId !== activeSwipePointerId) return;
  activeSwipePointerId = null;
  const start = swipeStartPoint;
  const drag = engagedDrag;
  swipeStartPoint = null;
  engagedDrag = null;
  if (start === null || drag === null) return;
  const deltaX = event.screenX - start.x;
  if (drag.kind === "select") {
    const committed = Math.abs(deltaX) > slotWidthPx() * COMMIT_FRACTION;
    pool?.endCarouselDrag(drag.targetChatId, drag.restOffsetPx, committed);
    if (committed) select(drag.targetChatId);
  } else {
    pool?.endResistDrag();
    if (drag.isAtNewChatEdge && Math.abs(deltaX) > slotWidthPx() * COMMIT_FRACTION) {
      isAtNewChatEdge = true;
      m.redraw();
    }
  }
}

/** A cancelled gesture (a system interruption -- an incoming call, the app backgrounded mid-drag) settles
 *  exactly like releasing short of the commit threshold: snap back, nothing committed. */
function onFramePointerCancel(event: PointerEvent): void {
  if (event.pointerId !== activeSwipePointerId) return;
  activeSwipePointerId = null;
  const drag = engagedDrag;
  swipeStartPoint = null;
  engagedDrag = null;
  if (drag === null) return;
  if (drag.kind === "select") pool?.endCarouselDrag(drag.targetChatId, drag.restOffsetPx, false);
  else pool?.endResistDrag();
}

/** Show ``chatId`` once the pending intake is applied or given up, reporting the selection even when it is the one
 *  reported before the token path: the shell holds that path as this window's location until the root reports
 *  another. */
function settleIntake(chatId: string | null): void {
  pendingToken = null;
  reportedLocation = null;
  select(chatId);
}

/** Put ``text`` in a chat's composer, unsent: the live page's when it is loaded, else where the composer reads
 *  its persisted draft on mount. Either way an element reference in it is attached as a file (the page's
 *  ``prependToComposer`` does it, and so does this document's, which the page's store reads on load). */
function draftInto(chatId: string, text: string): void {
  if (pool?.draftInto(chatId, text) === true) return;
  prependToComposer(chatId, text);
}

/** Launch a chat awaiting its first send with ``text`` (an intake that could not launch it at once): on the account
 *  the chat was minted for when it names one, else the signed-in account when one has appeared meanwhile, else
 *  through the provider chooser, as the composer's first send does; a dismissed chooser leaves the text in the
 *  composer, where the next send offers the chooser again. A chooser already open (for the New chat button) takes
 *  no second intent, so the text goes to the composer at once. */
async function launchWithFirstMessage(chatId: string, text: string): Promise<void> {
  const launchOrDraft = (accountId: string): void => {
    launchChat(chatId, accountId, text).catch((error: unknown) => {
      alert(`Failed to start the chat: ${(error as Error).message}`);
      draftInto(chatId, text);
    });
  };
  await whenAccountsReadyToChoose();
  const minted = getProvisionalChats().find((chat) => chat.chat_id === chatId);
  const account = accountForFirstSend(minted?.account_id);
  if (account !== null) {
    launchOrDraft(account.id);
    return;
  }
  if (isProviderChooserOpen()) {
    draftInto(chatId, text);
    return;
  }
  openProviderChooser({ onSignedIn: launchOrDraft, onDismissed: () => draftInto(chatId, text) });
}

/** A reference drafted from the root's own chrome (the rail, the empty slot): into the selected chat's composer,
 *  else through the shell, which lands it in the chat on screen (element-reference-menu plan section 3.4). */
function draftReference(text: string): void {
  if (selectedChatId !== null) {
    draftInto(selectedChatId, text);
    return;
  }
  connection?.draftText(text);
}

/** Whether a reference drafted from the root has somewhere to go: a selected chat, or a shell to ask. */
function isReferenceDraftAvailable(): boolean {
  return selectedChatId !== null || (connection?.isFramed ?? false);
}

/** What an applied intake asks of the root (post-launch-paths plan section 3.6.1): the chat is selected, a draft
 *  goes into its composer, a first message launches it. */
function takeApplied(applied: AppliedIntake): void {
  startedHere.add(applied.chatId);
  settleIntake(applied.chatId);
  if (applied.composerText !== null) draftInto(applied.chatId, applied.composerText);
  if (applied.firstMessage !== null) void launchWithFirstMessage(applied.chatId, applied.firstMessage);
}

/** Apply a held intake on the chat it resolved to, or on ``pickedChatId``; a token already gone (another client
 *  applied it, or it expired) leaves the chat shown as it stands, which for a token path naming a chat is that
 *  chat. */
async function applyIntake(token: string, pickedChatId: string | null): Promise<void> {
  try {
    takeApplied(await applyPendingIntake(token, pickedChatId));
  } catch (error) {
    if (!(error instanceof PendingIntakeGoneError)) alert(`Could not take the message: ${(error as Error).message}`);
    settleIntake(selectedChatId);
  }
}

/** The ``intake`` the root's URL carries: fetched, then applied at once, or offered through the picker when the
 *  chat is the user's to choose. Once applied or given up (a pick, a dismissal, a token already gone), the root
 *  reports the selection alone, so the window's stored path drops the token and a reload applies nothing again;
 *  while the picker is open the selection and the token path stand as they are. */
async function takeIntake(token: string): Promise<void> {
  let intake: PendingIntake;
  try {
    intake = await fetchPendingIntake(token);
  } catch (error) {
    if (!(error instanceof PendingIntakeGoneError)) alert(`Could not read the message: ${(error as Error).message}`);
    settleIntake(selectedChatId);
    return;
  }
  if (intake.needsPick) {
    pendingPick = { token, intake };
    m.redraw();
    return;
  }
  await applyIntake(token, null);
}

function pickFor(chatId: string): void {
  const pick = pendingPick;
  pendingPick = null;
  if (pick === null) return;
  void applyIntake(pick.token, chatId);
}

function dismissPick(): void {
  const pick = pendingPick;
  pendingPick = null;
  if (pick !== null) void discardPendingIntake(pick.token);
  settleIntake(selectedChatId);
}

function onChatsUpdated(): void {
  const rows = rowsFromSnapshots(getChats(), getProvisionalChats());
  noteStatuses(new Map(rows.map((row) => [row.chatId, row.status])), isRootShown ? selectedChatId : null);
  // A chat that has messaged is no longer new; a deleted chat's frame goes with it.
  for (const chatId of startedHere) {
    if (rows.some((row) => row.chatId === chatId && row.lastActiveMs !== null)) startedHere.delete(chatId);
  }
  const listed = new Set(rows.map((row) => row.chatId));
  for (const chatId of listed) awaitingListing.delete(chatId);
  const isKept = (chatId: string): boolean => listed.has(chatId) || awaitingListing.has(chatId);
  if (pool !== null) {
    for (const heldId of pool.heldChatIds()) {
      if (!isKept(heldId)) pool.destroy(heldId);
    }
  }
  if (selectedChatId !== null && !isKept(selectedChatId)) {
    select(null);
    return;
  }
  fillSlot();
  reportLocation();
}

const ChatRoot: m.Component = {
  view() {
    const rows = railRows();
    const isCompact = compactQuery.matches;
    const rail = railAttrs(rows, isCompact);
    return m(
      "div",
      {
        class: ["chat-root relative flex h-screen w-screen overflow-hidden bg-page", isCompact ? "flex-col" : ""].join(
          " ",
        ),
        "data-compact": isCompact ? "true" : "false",
      },
      [
        // The slot stays the second child in both layouts, so its frames outlive a change between them.
        isCompact
          ? m(ChatHeader, {
              row: rows.find((row) => row.chatId === selectedChatId) ?? null,
              context: rail,
              isListOpen: isDrawerOpen,
              onOpenList: () => {
                isDrawerOpen = true;
              },
            })
          : m(ChatRail, rail),
        m(
          "div",
          { class: "chat-root-slot relative min-h-0 min-w-0 flex-1" },
          [
            m("div", {
              class: "chat-root-frames absolute inset-0",
              // The frames are the pool's DOM, not mithril's: never reconciled.
              oncreate: ({ dom }: m.VnodeDOM) => {
                pool = new InnerFramePool(dom as HTMLElement);
                pool.setCompact(isCompact);
                if (handshake !== null) pool.setHandshake(handshake);
                pool.setRootShown(isRootShown);
                // Swipe-between-chats (phone layout only; a mouse drag on the desktop layout is left to the
                // rail): the gesture happens inside a frame's own document, so the pool binds it there.
                pool.setSwipeHandlers({
                  onPointerDown: onFramePointerDown,
                  onPointerMove: onFramePointerMove,
                  onPointerUp: onFramePointerUp,
                  onPointerCancel: onFramePointerCancel,
                });
                pool.show(selectedChatId);
              },
              onremove: () => {
                pool = null;
              },
              onbeforeupdate: () => false,
            }),
            selectedChatId === null
              ? m(
                  "div",
                  {
                    class:
                      "chat-root-empty absolute inset-0 flex items-center justify-center text-(length:--font-size-body) text-secondary",
                  },
                  "Pick a chat, or start a new one.",
                )
              : null,
            isCompact && isAtNewChatEdge
              ? m(
                  "div",
                  {
                    class: "chat-root-swipe-edge absolute inset-0 flex items-end justify-center bg-black/30 pb-8",
                    onclick: () => {
                      isAtNewChatEdge = false;
                      m.redraw();
                    },
                  },
                  m(
                    "button",
                    {
                      type: "button",
                      class:
                        "chat-root-swipe-edge-new flex items-center gap-2 rounded-full bg-accent px-5 py-3 " +
                        "text-(length:--font-size-body) font-semibold text-on-accent shadow-lg",
                      "aria-label": "New chat",
                      onclick: (event: MouseEvent) => {
                        event.stopPropagation();
                        void startNewChat();
                      },
                    },
                    [plusGlyph(18), m("span", "New chat")],
                  ),
                )
              : null,
          ],
        ),
        isCompact && isDrawerOpen
          ? m(ChatDrawer, {
              rail,
              isCovered: isProviderChooserOpen() || pendingPick !== null,
              onDismiss: () => {
                isDrawerOpen = false;
              },
            })
          : null,
        isProviderChooserOpen() ? m(ProviderChooserModal, { onDismiss: closeProviderChooser }) : null,
        pendingPick === null
          ? null
          : m(SendPicker, {
              rows,
              text: pendingPick.intake.message,
              isDraft: pendingPick.intake.isDraft,
              onPick: pickFor,
              onDismiss: dismissPick,
            }),
      ],
    );
  },
};

function railAttrs(rows: readonly ChatRow[], isCompact: boolean): ChatRailAttrs {
  return {
    rows,
    selectedChatId,
    isCompact,
    onPick: (chatId: string) => select(chatId),
    onNew: () => void startNewChat(),
    referenceScope: scopeOfHandshake(handshake),
    onDraftReference: draftReference,
    isReferenceDraftAvailable: isReferenceDraftAvailable(),
  };
}

/** Run ``take`` once the chats have arrived (which chat an intake lands on is decided against them) and the
 *  accounts have loaded (a launch before they load would run on none). */
function onceListedAndAccountsLoaded(accountsLoaded: Promise<void>, take: () => void): void {
  const onceListed = (): void => {
    removeChatsUpdatedListener(onceListed);
    void accountsLoaded.then(take);
  };
  addChatsUpdatedListener(onceListed);
}

function connectRootToShell(accountsLoaded: Promise<void>): ShellConnection {
  const shell = connectToShell({
    capabilities: { navigation: true, closeChord: false },
    onHandshake: (received) => {
      handshake = received;
      adoptClientIdentity({ clientId: received.clientId, desktopId: received.desktopId });
      pool?.setHandshake(received);
      // Whatever went up before the shell was listening is told again.
      reportedLocation = null;
      reportLocation();
      m.redraw();
    },
    onShown: () => {
      isRootShown = true;
      pool?.setRootShown(true);
      if (selectedChatId !== null) markRead(selectedChatId);
      fillSlot();
      m.redraw();
    },
    onHidden: () => {
      isRootShown = false;
      pool?.setRootShown(false);
      m.redraw();
    },
    onNavigate: (path) => {
      const target = new URL(path, window.location.origin);
      const token = intakeTokenFromSearch(target.search);
      const requested = selectionFromSearch(target.search);
      if (token !== null) {
        // The window is at the chat's path already; a picker path names none and leaves the shown chat standing.
        pendingToken = token;
        if (requested !== null) select(requested);
        void accountsLoaded.then(() => takeIntake(token));
        return;
      }
      select(requested);
    },
  });
  connection = shell;
  // Hidden until the shell says shown: the root can load into a background tab.
  if (shell.isFramed) isRootShown = false;
  window.addEventListener("focus", () => shell.focused());
  return shell;
}

function bootstrap(): void {
  initChatUnread();
  initChats();
  const accountsLoaded = loadAccountsWithRetry();
  addChatsUpdatedListener(onChatsUpdated);
  compactQuery.addEventListener("change", () => {
    pool?.setCompact(compactQuery.matches);
    fillSlot();
    m.redraw();
  });
  const shell = connectRootToShell(accountsLoaded);
  startInnerFrameRelay(
    (source) => pool?.isInnerWindow(source) ?? false,
    (chatId) => select(chatId),
  );
  const rootElement = document.getElementById("app");
  if (rootElement === null) return;
  selectedChatId = selectionFromSearch(window.location.search);
  isDrawerOpen = selectedChatId === null;
  pendingToken = intakeTokenFromSearch(window.location.search);
  m.mount(rootElement, ChatRoot);
  // The element menu over the root's own chrome (element-reference-menu plan section 7.3); the rail's rows append
  // the reference rows to their own menu instead.
  installElementContextMenu({
    connection: shell,
    handshake: () => handshake,
    draft: draftReference,
    isDraftAvailable: isReferenceDraftAvailable,
    open: createContextMenuOpener().open,
  });
  // The pointer hides while text is typed into the root's own fields (the send picker); the inner
  // chat frame does the same for itself.
  installCursorHidingWhileTyping(document);
  reportLocation();
  const token = pendingToken;
  if (token !== null) onceListedAndAccountsLoaded(accountsLoaded, () => void takeIntake(token));
}

window.addEventListener("load", bootstrap);
