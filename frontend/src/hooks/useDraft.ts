import { useCallback, useState } from "react";

/**
 * Text-field state that survives tab switches, reloads and restarts ("drafts are never
 * lost"). The value is read from localStorage before first paint and written on every
 * change; call `clear` only after a successful submit or an explicit discard. `clear(keep)`
 * drops the stored draft but leaves `keep` on screen (for fields that stay visible after
 * saving, like rating notes).
 *
 * Keys are `draft:<page>:<field>[:<record id>]`, e.g. `draft:rating:42:note`.
 */
const PREFIX = "draft:";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    if (value === "") window.localStorage.removeItem(PREFIX + key);
    else window.localStorage.setItem(PREFIX + key, value);
  } catch {
    /* private mode / quota: the field still works, it just won't persist */
  }
}

export function useDraft(
  key: string,
  initial: string = ""
): [string, (value: string) => void, (keep?: string) => void] {
  const [value, setValueState] = useState<string>(() => read(key) ?? initial);

  const setValue = useCallback(
    (next: string) => {
      setValueState(next);
      write(key, next);
    },
    [key]
  );

  const clear = useCallback(
    (keep: string = "") => {
      setValueState(keep);
      write(key, "");
    },
    [key]
  );

  return [value, setValue, clear];
}
