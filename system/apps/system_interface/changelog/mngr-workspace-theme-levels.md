An app the workspace built can be made themeable and then take the workspace's theme from outside, turned on and off by the user.

- The window menu's Theming submenu offers On and Off for a themeable app (`[theming] mode = "outside"`), with theming on by default. Changing it reloads the app's open pages.

- For an app that is not themeable yet, On and Off are greyed and "Enable theming" drafts a request into the main chat to make it themeable, following `docs/system/themeable-apps.md`. Such an app takes no theme until then.

- Imbue Studio's Theming keys: Option-Command-Right and -Left step the theme on screen, -Up and -Down turn the focused app's theming on and off, each with a notice saying where it is now.

- `POST /api/apps/<app>/theme-level` takes `light` (on) or `none` (off) for a themeable app, kept in `app_theme_levels.json`. The inventory carries each app's `theme_level` and `is_themeable`, and the shell serves the theme files under `/__workspace_theme/` that Imbue Studio's proxy puts into a themeable app's pages, with the workspace's default theme set in `kit.js` for a page the shell does not frame itself.

- A themeable app's theming is either on (light) or off (none): a level stored by an earlier build (medium or heavy) reads as on.
