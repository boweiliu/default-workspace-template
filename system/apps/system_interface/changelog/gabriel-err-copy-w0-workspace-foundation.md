Failure toasts on the workspace desktop can now be read and acted on.

- A toast that carries details or a button stays until it is dismissed, with a close control, its buttons (such as "Report a bug"), and a collapsed "See details" holding the status and the server's own text. A plain note still leaves after five seconds.

- A failed launch names the app by its display name: "Chat couldn't open that. Try again. If this persists, report a bug." (with a "Report a bug" button), or the app's own sentence when its refusal carries one for people. The app's reason is now passed on for any status, not only a 4xx, and sits behind "See details" instead of in the toast ("chat answered the launch with 503 instead of a page path").

- The desktop's fallbacks follow the shared set: no more bare "HTTP 500", and no claim that "nothing was changed" after a gateway status.
