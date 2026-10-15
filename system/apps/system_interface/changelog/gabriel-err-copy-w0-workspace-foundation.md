Failure toasts on the workspace desktop can now be read and acted on.

- Each failure says whether its toast stays: a failure whose retry is the control just pressed (closing a window, moving or removing a shortcut, a link) leaves a plain note that goes after five seconds; a launch, a failed startup read, a quit and a page's own move leave a toast that stays until dismissed, with a close control, a collapsed "See details" holding the status and the server's own text, and "Report a bug" where the sentence asks for one and the desktop app opens its bug report. The same toast twice replaces the first, and at most three lasting toasts stay on screen.

- A failed launch names the app by its display name: an app's refusal reads "Docs couldn't open that.", and an app that could not answer reads "Docs couldn't open that. Try again. If this persists, report a bug.", with the app's reason behind "See details"; an app's own sentence for people is shown as written. The shell now passes the app's reason on for any status and writes no sentence of its own.

- Failures no longer read "Could not close the window: <the shell's reason>": the reason goes behind "See details", and a request that got no answer says so on its own.
