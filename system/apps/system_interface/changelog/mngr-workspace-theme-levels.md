Apps whose manifest declares no `[theming]` now take the workspace's theme from outside, at a level set per app.

- The window menu has a Theme submenu with None, Light (the default: only unstyled controls), Medium (fills in only what the app left unset), and Heavy (the theme's values win). Changing the level reloads the app's open pages.

- "Restyle with AI..." and "Re-imagine with AI..." in the same submenu draft a request in the pinned chat: one rewrites the app on the design tokens, the other redesigns it, assets included, for the theme.

- `POST /api/apps/<app>/theme-level` sets an app's level, kept in `app_theme_levels.json`. The inventory carries each such app's `theme_level`, and the shell serves the theme files under `/__workspace_theme/` that Imbue Studio's proxy puts into the app's pages. An app that themes itself, and a service the registry does not know, get no theme.
