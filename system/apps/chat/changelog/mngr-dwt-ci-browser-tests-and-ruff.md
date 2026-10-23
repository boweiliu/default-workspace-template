The long-chat wheel test waits for each tick's motion to land instead of a fixed 50 ms, which failed on slower machines while the chat was still measuring its history. It still fails if a tick makes the transcript jump.

Fixed the app's `ruff check` findings, which CI now enforces: two import blocks, three lambda assignments in tests, and a `noqa` on seven deliberate no-op hook methods. The trailing-comment ratchet rises from 2 to 9 for those `noqa` directives, which it does not yet exempt the way it exempts `# ty: ignore`. No behavior change.
