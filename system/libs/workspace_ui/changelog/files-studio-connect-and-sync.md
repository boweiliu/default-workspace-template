The app contract and the embed contract carry what Files needs to connect a file or folder through Imbue Studio.

- `shell:handshake` has an `opensLocalFiles` flag, read as false when the shell does not send it: whether the Imbue Studio chrome opens its own file picker to share something with the workspace.
- `embed.ts` probes the contract v9 pair, `minds:open-local-files` (workspace to embedder) and `minds:open-local-files-ack` with `added` (embedder to workspace), and dispatches the ack like the other embedder messages.
- A tooltip can carry an optional second line in quieter text under the first (`hoverTooltipAttrs(text, placement, { detail })`), for a detail worth a glance -- a reason, a time -- without stretching the first line. A tooltip without one is unchanged.
