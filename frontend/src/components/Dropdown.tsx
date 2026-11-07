import { Fragment, KeyboardEvent, useEffect, useId, useRef, useState } from "react";

export interface DropdownOption {
  value: string;
  label: string;
  group?: string;
}

export function Dropdown({
  ariaLabel,
  value,
  options,
  onChange,
}: {
  ariaLabel: string;
  value: string;
  options: DropdownOption[];
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const selected = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open]);

  function keyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      trigger.current?.focus();
      return;
    }
    if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      setOpen(true);
    }
  }

  return (
    <div className={"dropdown" + (open ? " open" : "")} ref={root} onKeyDown={keyDown}>
      <button
        ref={trigger}
        type="button"
        className="dropdown-trigger"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((current) => !current)}
      >
        <span>{selected?.label}</span>
        <i className="dropdown-chevron" aria-hidden="true" />
      </button>
      {open && (
        <div className="dropdown-menu" id={menuId} role="listbox" aria-label={ariaLabel}>
          {options.map((option, index) => {
            const previousGroup = index > 0 ? options[index - 1].group : undefined;
            const showGroup = option.group && option.group !== previousGroup;
            return (
              <Fragment key={option.value}>
                {showGroup && <div className="dropdown-group">{option.group}</div>}
                <button
                  type="button"
                  className="dropdown-option"
                  role="option"
                  aria-selected={option.value === value}
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                    trigger.current?.focus();
                  }}
                >
                  {option.label}
                  {option.value === value && <span aria-hidden="true">✓</span>}
                </button>
              </Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
}
