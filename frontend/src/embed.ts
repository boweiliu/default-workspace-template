/**
 * This app's single connection to an optional embedding host frame.
 *
 * All postMessage traffic with a host flows through `./embed-contract.ts`
 * (a small, documented, host-agnostic protocol -- see that file); this
 * module owns the one app-side endpoint and hands out narrow send/subscribe
 * helpers. Raw `postMessage` / `message`-listener usage anywhere else in
 * this app should go through here instead, so the whole boundary stays in
 * one place.
 *
 * The app behaves identically embedded (iframe under a host) and top-level
 * (opened directly): with no host, outbound sends simply have no listener
 * and no host message ever arrives.
 */

import { PERMISSION_RESOLUTIONS, createEmbedEndpoint, type ContractEndpoint, type ContractMessage } from "./embed-contract";

export { PERMISSION_RESOLUTIONS };
export type { ContractMessage };

type EmbedderMessageHandler = (message: ContractMessage) => void;

// One replaceable handler per host->app type, registered by the feature that
// owns it (the permission cards register the resolution relay at boot).
const handlerByType: Partial<Record<string, EmbedderMessageHandler>> = {};

// Created on first use rather than at import time so importing this module
// never touches `window` (unit tests run under node and stub it per test).
let endpoint: ContractEndpoint | null = null;

// A do-nothing endpoint for non-browser contexts: component unit tests run
// under node without a `window`, and features send/subscribe unconditionally.
const NULL_ENDPOINT: ContractEndpoint = {
  send: () => undefined,
  dispose: () => undefined,
};

function getEndpoint(): ContractEndpoint {
  if (endpoint === null) {
    if (typeof window === "undefined") return NULL_ENDPOINT;
    endpoint = createEmbedEndpoint({
      [PERMISSION_RESOLUTIONS]: (message) => handlerByType[PERMISSION_RESOLUTIONS]?.(message),
    });
  }
  return endpoint;
}

/** Send an app->host contract message (no-op when not embedded, or no host present). */
export function sendToEmbedder(type: string, payload?: Record<string, unknown>): void {
  getEndpoint().send(type, payload);
}

/** Register the handler for one host->app type (replaces any prior one). */
export function setEmbedderMessageHandler(type: string, handler: EmbedderMessageHandler): void {
  getEndpoint();
  handlerByType[type] = handler;
}

/** Clear the handler for one host->app type. */
export function clearEmbedderMessageHandler(type: string): void {
  delete handlerByType[type];
}

/** Tear the endpoint down so the next use rebinds to the current `window`. Test-only. */
export function resetEmbedEndpointForTesting(): void {
  if (endpoint !== null) {
    endpoint.dispose();
    endpoint = null;
  }
  for (const type of Object.keys(handlerByType)) delete handlerByType[type];
}
