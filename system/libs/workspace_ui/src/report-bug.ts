/**
 * "Report a bug": the button a failure whose sentence asks for one carries. It opens Imbue Studio's bug report (its
 * Get help page) over this workspace, so it is offered only where the embedder said it opens one (``opensHelp``); the
 * sentence still says "report a bug" everywhere.
 */

import { OPEN_HELP } from "@minds/embed-contract";
import type { NoticeAction } from "./components/NoticeDialog";
import { embedderOpensHelp, sendToEmbedder } from "./embed";

export const REPORT_A_BUG_LABEL = "Report a bug";

export function openBugReport(): void {
  sendToEmbedder(OPEN_HELP);
}

/** Whether a "Report a bug" button would do anything here. */
export function canReportBug(): boolean {
  return embedderOpensHelp();
}

/** A notice's "Report a bug" action, when its sentence asks for one and the embedder can open the bug report. */
export function reportBugActions(isReportable: boolean): readonly NoticeAction[] {
  return isReportable && canReportBug() ? [{ label: REPORT_A_BUG_LABEL, isSecondary: true, run: openBugReport }] : [];
}
