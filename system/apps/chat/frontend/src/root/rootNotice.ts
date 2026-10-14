/**
 * The chat root's one notice: a failure of something done from the chat list (stop, restart, delete) or of a
 * message sent from outside a chat, told in a styled dialog over the list rather than a browser alert. Our sentence
 * on screen, the server's text behind "See details", Try again where repeating the operation can help, and "Report
 * a bug" when the sentence asks for one.
 */

import m from "mithril";
import { makeNoticeDialog } from "@imbue/workspace-ui/src/components/NoticeDialog";
import { REPORT_A_BUG_ENDING } from "@imbue/workspace-ui/src/models/failure";
import { describeRequestFailure } from "@imbue/workspace-ui/src/models/request-error";
import { reportBugAction } from "@imbue/workspace-ui/src/report-bug";
import { detailsBehind } from "../views/failure-lines";
import type { FailureLines } from "../views/failure-lines";

export interface RootNotice {
  readonly title: string;
  readonly lines: FailureLines;
  /** Repeats the operation; null when repeating it cannot help or is not safe. */
  readonly retry: (() => void) | null;
}

let current: RootNotice | null = null;

export function raiseRootNotice(notice: RootNotice): void {
  current = notice;
  m.redraw();
}

function closeRootNotice(): void {
  current = null;
  m.redraw();
}

/** Mounted once by the chat root, over everything else. */
export function RootNoticeView(): m.Component {
  const dialog = makeNoticeDialog();
  return {
    view() {
      const notice = current;
      if (notice === null) return null;
      const retry = notice.retry;
      return m(dialog, {
        title: notice.title,
        body: notice.lines.body,
        details: notice.lines.details,
        dismissLabel: retry === null ? "OK" : "Cancel",
        onDismiss: closeRootNotice,
        actions: [
          ...(notice.lines.isReportable ? [reportBugAction()] : []),
          ...(retry === null
            ? []
            : [
                {
                  label: "Try again",
                  run: () => {
                    closeRootNotice();
                    retry();
                  },
                },
              ]),
        ],
      });
    },
  };
}

/** A Stop chat or Restart chat from the list, refused or unanswered. */
export function describeRunVerbFailure(error: unknown, title: string, isRestart: boolean): FailureLines {
  const failure = describeRequestFailure(error);
  const named = `"${title}"`;
  if (failure.isNotAnswered) {
    return {
      body: [
        `The workspace didn't answer, so Imbue Studio can't tell whether ${named} ${isRestart ? "restarted" : "stopped"}.`,
      ],
      details: failure.details,
      isReportable: false,
    };
  }
  const lead = isRestart
    ? `Couldn't restart ${named}. It's still stopped.`
    : `Couldn't stop ${named}. It's still running.`;
  if (failure.isUserFacing) {
    return { body: [lead, failure.message], details: failure.details, isReportable: failure.isReportable };
  }
  return { body: [`${lead} ${REPORT_A_BUG_ENDING}`], details: detailsBehind(failure), isReportable: true };
}

/** A Delete chat from the list, refused or unanswered. */
export function describeDeleteFailure(error: unknown, title: string): FailureLines {
  const failure = describeRequestFailure(error);
  const named = `"${title}"`;
  if (failure.isNotAnswered) {
    return {
      body: [`The workspace didn't answer, so Imbue Studio can't tell whether ${named} was deleted.`],
      details: failure.details,
      isReportable: false,
    };
  }
  if (failure.isUserFacing) {
    return { body: [failure.message], details: failure.details, isReportable: failure.isReportable };
  }
  return {
    body: [`Couldn't delete ${named}. It's still here. ${REPORT_A_BUG_ENDING}`],
    details: detailsBehind(failure),
    isReportable: true,
  };
}

/** A message sent from outside a chat (the launcher, a desktop draft) that the chat would not take, or that got no
 *  answer; ``isDrafted`` when it was put back in the chat's composer. */
export function describeIntakeApplyFailure(error: unknown, isDrafted: boolean): FailureLines {
  const failure = describeRequestFailure(error);
  if (failure.isNotAnswered) {
    return {
      body: ["The workspace didn't answer, so Imbue Studio can't tell whether your message reached this chat."],
      details: failure.details,
      isReportable: false,
    };
  }
  return {
    body: [
      isDrafted
        ? "Your message couldn't be sent to this chat. It's in the box below."
        : "Your message couldn't be sent to a chat.",
      failure.isUserFacing ? failure.message : null,
    ],
    details: detailsBehind(failure),
    isReportable: failure.isReportable,
  };
}
