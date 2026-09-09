/**
 * A documented, host-agnostic postMessage protocol for embedding this app
 * inside a trusted parent frame (e.g. a workspace shell). This is NOT a
 * client for any specific product -- it is a small, self-contained
 * reimplementation of the two message shapes this app actually sends/expects
 * (a permission-request modal handoff, and a permission-resolution sync), so
 * a compatible host can be built against it without this repo vendoring or
 * depending on that host's own code. Treat "a host that speaks this
 * protocol" the same way you'd treat any other external API dependency
 * (like the chat backend -- see the root README): optional, documented, and
 * swappable, never a hard code dependency.
 *
 * With no parent frame (the common case -- this app opened directly in a
 * browser tab), sends simply have no listener and no host message ever
 * arrives; every feature built on this degrades to "the host isn't here."
 *
 * Wire shape: `{ type: string, ...payload }`, posted with `targetOrigin: "*"`
 * (a host that cares about origin must check `event.origin` itself; this
 * side only checks that the message's `source` is `window.parent`).
 * Unknown message types are ignored. If you add a message type, document its
 * payload shape here, next to the others.
 */

// app -> host: ask the host to open its own permission-request review UI,
// focused on one request. Payload: `{ requestId: string }`.
export const OPEN_REQUEST_MODAL = "embed:open-request-modal";

// host -> app: permission-request verdicts the host knows about, each entry
// `{ requestId: string, resolution: "granted" | "denied" }`. Sent as a
// snapshot whenever this app's frame (re)loads, and/or as a single
// unsolicited entry the moment the host resolves a request elsewhere.
// Payload: `{ resolutions: Array<{ requestId: string, resolution: "granted" | "denied" }> }`.
export const PERMISSION_RESOLUTIONS = "embed:permission-resolutions";

export interface ContractMessage {
  type: string;
  [key: string]: unknown;
}

type MessageHandler = (message: ContractMessage) => void;

export interface ContractEndpoint {
  send(type: string, payload?: Record<string, unknown>): void;
  dispose(): void;
}

/**
 * Open this app's side of the contract: listens for host -> app messages
 * (only from `window.parent`) and returns `{ send, dispose }` for app -> host
 * messages. Safe to call with no host present -- `send` then just posts into
 * the void, and no message ever arrives to dispatch.
 */
export function createEmbedEndpoint(handlers: Partial<Record<string, MessageHandler>>): ContractEndpoint {
  const boundWindow = window;

  function onMessage(event: MessageEvent): void {
    if (event.source !== boundWindow.parent) return;
    const data = event.data as unknown;
    if (!data || typeof data !== "object" || typeof (data as ContractMessage).type !== "string") return;
    const message = data as ContractMessage;
    handlers[message.type]?.(message);
  }

  boundWindow.addEventListener("message", onMessage);
  return {
    send(type, payload) {
      boundWindow.parent.postMessage({ type, ...payload }, "*");
    },
    dispose() {
      boundWindow.removeEventListener("message", onMessage);
    },
  };
}
