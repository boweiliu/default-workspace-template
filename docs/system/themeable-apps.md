# Making an app themeable

The user can dress the workspace in a theme (Desktop settings > Theme): the standard look,
Classic Mac, Windows 2000, or one they made. An app the workspace built takes the theme from
outside, with no work of its own: the page it serves gets the theme's design tokens and styles put
into it, at the level the user chose for the app in its window menu's Theming submenu (none,
light, medium, or heavy). The design is
`docs/system/blueprint/workspace-themes/plan-workspace-themes.md`, sections 4 and 7.1.

What that reaches depends on how the app is written. A literal color or font the app sets is one
no theme can change. Making the app themeable means writing its look so every theme reaches it,
while it keeps the look it has today when theming is off.

## Leave the app's manifest alone

Keep `app.toml` without a `[theming]` table. An app with no `[theming]` is the kind the
workspace themes from outside; declaring a mode turns that off, and the app would then have to
load the theme itself.

## Take every color, font, radius, and shadow from a token

Replace each literal in the app's CSS, markup, and scripts with the matching token, written with
today's value as the fallback, so the app looks as it does now when no theme is put in:

```css
.card { background: var(--c-surface, #ffffff); color: var(--c-text-primary, #2a2522); }
```

- Colors: every `--c-*` in `system/libs/workspace_ui/src/base.css`: `--c-bg`, `--c-surface`,
  `--c-text-primary`, `--c-text-secondary`, `--c-border`, `--c-accent`, `--c-danger`, and the
  rest there.
- Type: `--font-sans` for text, `--font-display` for headings, `--font-mono` for code, and the
  `--font-size-*` and `--weight-*` steps.
- Shape: `--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-xl`, and the `--c-shadow-*`
  shadows.

Pick each token by what the value means, not by matching colors: the app's own accent is
`--c-accent`, its page background `--c-bg`. Never copy the current theme's values into the app;
the point is that the app changes when the theme does.

An app that defines its own variables (`--accent: #d26645;`) can keep them, defined from the
tokens: `--accent: var(--c-accent, #d26645);`.

## Keep controls plain

The theme dresses a `<button>`, a text `<input>`, a `<textarea>`, and a `<select>` that carry no
`class` and no `style` attribute, at every level from light up. Write a control that should look
like the workspace's that way, and style its layout from its container instead
(`.toolbar > button { margin-left: 8px; }`). For emphasis, add `data-variant="primary"` (or
`ghost`, `destructive`); a button that is only an icon is `data-shape="icon"`.

A control that keeps a look of its own on purpose (a big colored call-to-action, a glyph-only
delete) can keep its class; it then takes the theme only through the tokens it uses.

## Check it

```bash
uv run workspace-themes lint-app <package>
```

lists every literal color, font family, and shadow still in the app's sources, by file and line.
Fix each, or leave it only where the app keeps a fixed look on purpose.

Then show the user the app in its window, and tell them they can step through the themes with
Option-Command-Right and -Left while they look.
