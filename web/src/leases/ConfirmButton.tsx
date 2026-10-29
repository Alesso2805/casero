import { useEffect, useRef, useState } from "react";

import { primaryButton, secondaryButton } from "../account/fields";

/** An action that can't be undone with one tap: it asks first, then confirms or cancels. */
export function ConfirmButton({
  id,
  label,
  question,
  confirmLabel,
  cancelLabel,
  busy,
  onConfirm,
}: {
  id: string;
  label: string;
  question: string;
  confirmLabel: string;
  cancelLabel: string;
  busy: boolean;
  onConfirm: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const confirm = useRef<HTMLButtonElement>(null);
  const cancelled = useRef(false);
  useEffect(() => {
    if (asking) {
      confirm.current?.focus();
    } else if (cancelled.current) {
      cancelled.current = false;
      trigger.current?.focus();
    }
  }, [asking]);
  if (!asking) {
    return (
      <button
        ref={trigger}
        type="button"
        className={secondaryButton}
        disabled={busy}
        onClick={() => {
          setAsking(true);
        }}
      >
        {label}
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <p id={`${id}-question`}>{question}</p>
      <button
        ref={confirm}
        type="button"
        className={primaryButton}
        aria-describedby={`${id}-question`}
        disabled={busy}
        onClick={onConfirm}
      >
        {confirmLabel}
      </button>
      <button
        type="button"
        className={secondaryButton}
        onClick={() => {
          cancelled.current = true;
          setAsking(false);
        }}
      >
        {cancelLabel}
      </button>
    </div>
  );
}
