"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export type PublishDestOption = {
  value: string;
  label: string;
  hint?: string;
};

export function PublishDestSelect({
  id,
  className,
  value,
  disabled,
  options,
  leading,
  labelledBy,
  onChange
}: {
  id?: string;
  className: string;
  value: string;
  disabled: boolean;
  options: PublishDestOption[];
  leading?: ReactNode;
  labelledBy?: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const selected = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    function onPointer(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className={`publish-draft-desk__dest-picker${open ? " is-open" : ""}`} ref={rootRef}>
      <button
        id={id}
        type="button"
        className={className}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={open ? listId : undefined}
        aria-labelledby={labelledBy}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        {leading}
        <span className="publish-draft-desk__channel-row">
          <span className="publish-draft-desk__dest-picker-value">{selected?.label ?? ""}</span>
        </span>
      </button>
      {open ? (
        <div className="publish-draft-desk__dest-menu" id={listId} role="listbox">
          {options.map((option) => {
            const active = option.value === value;
            return (
              <button
                key={option.value || "__empty"}
                type="button"
                role="option"
                aria-selected={active}
                className={`publish-draft-desk__dest-option${active ? " is-selected" : ""}`}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
              >
                <span className="publish-draft-desk__dest-option-label">{option.label}</span>
                {option.hint ? <span className="publish-draft-desk__dest-option-hint">{option.hint}</span> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
