import * as DialogPrimitive from '@radix-ui/react-dialog';
import { useRef, type ComponentProps } from 'react';

/** shadcn/ui-style Dialog on Radix (focus trap, Esc, initial focus). The overlay wraps the content (design .overlay grid). */
export const Dialog = DialogPrimitive.Root;
export const DialogClose = DialogPrimitive.Close;
export const DialogTitle = DialogPrimitive.Title;
export const DialogDescription = DialogPrimitive.Description;

/**
 * Dialogs here are opened from app state (button, double-click, shortcut), not from a Radix Trigger, so Radix has no
 * trigger to return focus to. The element focused when the dialog mounted is restored on close if it still exists.
 */
export function DialogContent({ className, children, onCloseAutoFocus, ...props }: ComponentProps<typeof DialogPrimitive.Content>) {
  const opener = useRef<HTMLElement | null>(typeof document !== 'undefined' ? (document.activeElement as HTMLElement | null) : null);
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="overlay">
        <DialogPrimitive.Content className={className} {...props}
          onCloseAutoFocus={(e) => {
            onCloseAutoFocus?.(e);
            if (e.defaultPrevented) return;
            const el = opener.current;
            if (el && el.isConnected && el !== document.body) { e.preventDefault(); el.focus(); }
          }}>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Overlay>
    </DialogPrimitive.Portal>
  );
}
