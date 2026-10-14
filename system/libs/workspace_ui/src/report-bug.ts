/**
 * "Report a bug": the button every failure that ends "If this persists, report a bug." carries. It opens Imbue
 * Studio's bug report (its Get help page) over this workspace; with no Imbue Studio around the page (a shared visit)
 * nothing is listening, so it does nothing.
 */

import { OPEN_HELP } from "@minds/embed-contract";
import type { NoticeAction } from "./components/NoticeDialog";
import { sendToEmbedder } from "./embed";

export const REPORT_A_BUG_LABEL = "Report a bug";

export function openBugReport(): void {
  sendToEmbedder(OPEN_HELP);
}

/** The "Report a bug" action of a notice whose sentence asks for one. */
export function reportBugAction(): NoticeAction {
  return { label: REPORT_A_BUG_LABEL, isSecondary: true, run: openBugReport };
}
