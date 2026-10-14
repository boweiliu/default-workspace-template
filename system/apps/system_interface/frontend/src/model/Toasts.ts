/**
 * The shell's toasts (plan-phone-interface.md): a failed operation says so in a short note that rises over the
 * desktop or above the phone's bar, instead of a browser ``alert()`` that stops everything until it is dismissed. A
 * note with nothing to press goes away on its own; one that carries details or a button stays until it is dismissed,
 * so its reason and its next step outlast the five seconds a plain note gets.
 */

export interface ToastAction {
  readonly label: string;
  readonly run: () => void;
}

export interface ToastOptions {
  /** What goes behind "See details"; none when null or absent. */
  readonly details?: string | null;
  /** Buttons after the message (Try again, Report a bug, ...), in order. */
  readonly actions?: readonly ToastAction[];
}

export interface Toast {
  readonly id: number;
  readonly message: string;
  readonly details: string | null;
  readonly actions: readonly ToastAction[];
  /** Stays until dismissed: it carries details or a button, which a note that leaves on its own cannot hold. */
  readonly isLasting: boolean;
}

/** How long a toast with nothing to press stays up. */
export const TOAST_DURATION_MS = 5000;

/** The toasts on screen, oldest first; a plain one leaves after ``durationMs``, every one when dismissed. */
export class ToastQueue {
  private toasts: readonly Toast[] = [];
  private nextId = 1;

  constructor(
    private readonly onChange: () => void,
    private readonly durationMs: number = TOAST_DURATION_MS,
  ) {}

  show(message: string, options: ToastOptions = {}): void {
    const details = options.details ?? null;
    const actions = options.actions ?? [];
    const isLasting = details !== null || actions.length > 0;
    const toast: Toast = { id: this.nextId, message, details, actions, isLasting };
    this.nextId += 1;
    this.toasts = [...this.toasts, toast];
    if (!isLasting) setTimeout(() => this.dismiss(toast.id), this.durationMs);
    this.onChange();
  }

  dismiss(id: number): void {
    if (!this.toasts.some((toast) => toast.id === id)) return;
    this.toasts = this.toasts.filter((toast) => toast.id !== id);
    this.onChange();
  }

  current(): readonly Toast[] {
    return this.toasts;
  }
}
