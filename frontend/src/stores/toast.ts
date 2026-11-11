import { create } from 'zustand';

/**
 * One toast at a time, bottom centre (design). `quiet` messages are only announced to screen readers.
 * A toast with an action (e.g. 되돌리기) stays longer and has a close button.
 */
export type ToastKind = 'info' | 'ok' | 'error';

export interface Toast {
  id: number;
  message: string;
  kind: ToastKind;
  action?: { label: string; run: () => void };
}

interface ToastStore {
  current: Toast | null;
  announcement: { id: number; text: string } | null;
  push: (message: string, kind?: ToastKind, action?: Toast['action']) => void;
  announce: (text: string) => void;
  dismiss: (id?: number) => void;
}

let seq = 0;
let timer: ReturnType<typeof setTimeout> | undefined;

export const useToasts = create<ToastStore>()((set, get) => ({
  current: null,
  announcement: null,
  push: (message, kind = 'info', action) => {
    const id = ++seq;
    clearTimeout(timer);
    set({ current: { id, message, kind, action } });
    timer = setTimeout(() => get().dismiss(id), action ? 7000 : kind === 'error' ? 4800 : 2600);
  },
  announce: (text) => set({ announcement: { id: ++seq, text } }),
  dismiss: (id) => {
    const cur = get().current;
    if (!cur || (id != null && cur.id !== id)) return;
    clearTimeout(timer);
    set({ current: null });
  },
}));

export const toast = (message: string, kind?: ToastKind) => useToasts.getState().push(message, kind);
export const snack = (message: string, label: string, run: () => void) => useToasts.getState().push(message, 'ok', { label, run });
export const announce = (text: string) => useToasts.getState().announce(text);
