import m from "mithril";

/** The chat's terminal back face: a frame on the terminal app, with the flags a terminal page needs.
 *  Its size and corner are `.terminal-frame` in the stylesheet.
 *
 *  Until the frame has loaded it paints nothing, so the card's own surface would show through; the
 *  terminal-styled line under it fills that wait instead. The frame's `load` waits for the pty page
 *  it nests, so it fires once the terminal itself is on screen. The frame keeps its size while
 *  hidden: ttyd fits its grid to the viewport it loads into. */
export function TerminalFrame(): m.Component<{ url: string; title: string }> {
  let loadedUrl: string | null = null;
  return {
    view(vnode) {
      const isLoaded = loadedUrl === vnode.attrs.url;
      return m("div", { class: "terminal-frame-box" }, [
        isLoaded
          ? null
          : m("div", { class: "terminal-frame-loading terminal-placeholder" }, "Opening the terminal..."),
        m("iframe", {
          src: vnode.attrs.url,
          title: vnode.attrs.title,
          class: isLoaded ? "terminal-frame" : "terminal-frame terminal-frame-pending",
          sandbox: "allow-scripts allow-same-origin allow-forms allow-popups",
          allow: "clipboard-read; clipboard-write",
          onload: () => {
            loadedUrl = vnode.attrs.url;
          },
        }),
      ]);
    },
  };
}
