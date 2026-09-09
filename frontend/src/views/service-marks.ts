/**
 * The bundled brand mark for a permission scope's service.
 *
 * The app this was forked from bundles real per-service logos via a
 * build-time glob into its monorepo's own icon set. This standalone fork
 * ships no such art, so every card falls back to the generic mark (see
 * `renderSubjectMark` in permission-card.ts) -- functionally fine, just
 * unbranded. Unlike the host-shell integration (embed.ts /
 * embed-contract.ts), there's no protocol to document here: it's just
 * bundled artwork this repo doesn't carry.
 */

/** Always null in this fork -- no marks are bundled. Kept so callers don't change. */
export function serviceMarkUrl(_scope: string): string | null {
  return null;
}
