A failed request inside a workspace is now told the same way everywhere: a sentence of ours on screen, and the status and the server's own text behind a collapsed "See details".

- One set of fallback sentences. A read that got no answer (a gateway status, a dropped connection, a timeout) says "The workspace didn't answer. Try again in a moment."; a change says "The workspace didn't answer, so Imbue Studio can't tell whether this went through." A refusal with no reason says "Something went wrong in this workspace." (REST helper) or "The workspace couldn't do that." (chat requests), followed by "Try again. If this persists, report a bug." These replace "HTTP 500", "request failed (HTTP 503)", "could not reach the workspace", "unknown error" and the gateway sentence that claimed "nothing was changed", which the workspace cannot know: Imbue Studio's forward proxy can send a gateway status after the request arrived.

- A route's `user_facing_message`, a sentence written for people, is shown as written in place of its `detail`.

- New pieces for the screens that adopt them: `SeeDetails` (also drawn by `NoticeDialog` from its new `details`), and `report-bug.ts`, whose "Report a bug" button opens Imbue Studio's bug report.
