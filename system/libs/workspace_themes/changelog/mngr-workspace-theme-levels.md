Serves the theme to an app's page that does not load it itself, at a level (`docs/system/blueprint/workspace-themes/plan-workspace-themes.md`, section 7.1).

- `register_injected_theme_routes` answers `/__workspace_theme/layers.css`, `kit.js`, `base.css`, and `themes/<id>/...` on any app's origin, for the app `X-Mngr-Forward-Service` names. At `none` the layer order and the script are both empty.

- `light` styles only unstyled elements: a control part's rules go to the bare `<button>`, text `<input>`, `<textarea>`, or `<select>` that has no `class` or `style`, and only the `:root` tokens are kept. `medium` puts the theme in the `workspace-theme` cascade layer, under everything the app styles itself. `heavy` makes every declaration `!important`.

- A theme's style file served the ordinary way no longer gives part rules a second selector for bare controls.

- `workspace-themes lint-app` checks an app's own `assets/` folder too, where build-app keeps a page's hand-written CSS and scripts; built output (`static/`, `dist/`, `build/`) is still skipped.

- `kit.js` carries the workspace's default theme (`register_injected_theme_routes`' `default_theme_id`), which a page wears first when its origin remembers none; a theme's plain files (a library's button picture) are served to injected pages with no level.

- `workspace-themes lint-app` lints outside-mode apps too, and takes a token's `var(--token, fallback)` fallback as the look the app keeps with no theme, not as a literal. An id selector that starts like a hex color (`#add-form`) is no longer read as one.
