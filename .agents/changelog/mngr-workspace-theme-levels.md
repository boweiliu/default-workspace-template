New `docs/system/themeable-apps.md`: how to make an app themeable (`[theming] mode = "outside"`, tokens with today's values as fallbacks, plain controls, `lint-app` to check). Only "Enable theming" points agents at it; app building does not read it.

A preview carries the app's `[theming]` mode from its worktree, and its page hands the shell's theme on to the app it frames, so the preview of a themeable app follows theme changes.

The guide has the agent ask about per-theme icons in the same reply that keeps the change, before any background check starts.
