// @vitest-environment jsdom
/**
 * The terminal frame's wait: until the frame has loaded, the terminal-styled line shows and the frame
 * is hidden (never removed, so it keeps its size); its load swaps them, and a new URL waits again.
 */
import { beforeEach, describe, expect, it } from "vitest";
import m from "mithril";

import { TerminalFrame } from "./TerminalFrame";

const attrs = { url: "http://terminal.localhost/?arg=_&arg=agent&arg=one", title: "one terminal" };

function mountFrame(): HTMLElement {
  const root = document.createElement("div");
  document.body.appendChild(root);
  m.mount(root, { view: () => m(TerminalFrame, attrs) });
  return root;
}

describe("the terminal frame's loading line", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    attrs.url = "http://terminal.localhost/?arg=_&arg=agent&arg=one";
  });

  it("shows the line over a hidden frame until the frame loads, then only the frame", () => {
    const root = mountFrame();
    const frame = root.querySelector("iframe") as HTMLIFrameElement;
    expect(root.querySelector(".terminal-frame-loading")?.textContent).toBe("Opening the terminal...");
    expect(frame.classList.contains("terminal-frame-pending")).toBe(true);

    frame.dispatchEvent(new Event("load"));
    m.redraw.sync();
    expect(root.querySelector(".terminal-frame-loading")).toBeNull();
    expect(root.querySelector("iframe")).toBe(frame);
    expect(frame.classList.contains("terminal-frame-pending")).toBe(false);
  });

  it("waits again when the frame is pointed at another terminal", () => {
    const root = mountFrame();
    root.querySelector("iframe")?.dispatchEvent(new Event("load"));
    m.redraw.sync();

    attrs.url = "http://terminal.localhost/?arg=_&arg=agent&arg=two";
    m.redraw.sync();
    expect(root.querySelector(".terminal-frame-loading")).not.toBeNull();
    expect(root.querySelector("iframe")?.classList.contains("terminal-frame-pending")).toBe(true);
  });
});
