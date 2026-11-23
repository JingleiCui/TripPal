import { useState, type SetStateAction, type Dispatch } from "react";

const PREFIX = "tripal-workspace:";
const clearedAccounts = new Set<string>();
export function activateWorkspaceState(accountId: string) {
  clearedAccounts.delete(accountId);
}
export function isWorkspaceActive(accountId: string) {
  return !clearedAccounts.has(accountId);
}
function isCleared(key: string) {
  return [...clearedAccounts].some((account) => key.startsWith(account + ":"));
}
export function readWorkspace<T>(key: string, fallback: T): T {
  if (isCleared(key)) return fallback;
  try {
    const value = localStorage.getItem(PREFIX + key);
    return value === null ? fallback : JSON.parse(value);
  } catch {
    return fallback;
  }
}

export function writeWorkspace<T>(key: string, value: T) {
  if (isCleared(key)) return;
  try {
    if (value === undefined) localStorage.removeItem(PREFIX + key);
    else localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    /* Browser storage is optional. */
  }
}

// A per-account, per-conversation UI snapshot. Server records remain authoritative.
export function useWorkspaceState<T>(
  key: string,
  fallback: T,
): [T, Dispatch<SetStateAction<T>>] {
  const [entry, setEntry] = useState(() => ({
    key,
    value: readWorkspace(key, fallback),
  }));
  if (entry.key !== key) setEntry({ key, value: readWorkspace(key, fallback) });
  const value = entry.key === key ? entry.value : readWorkspace(key, fallback);
  const setValue: Dispatch<SetStateAction<T>> = (action) => {
    setEntry((old) => {
      const previous = old.key === key ? old.value : readWorkspace(key, fallback);
      const next =
        typeof action === "function" ? (action as (v: T) => T)(previous) : action;
      writeWorkspace(key, next);
      return { key, value: next };
    });
  };
  return [value, setValue];
}

export function clearWorkspaceState(accountId?: string) {
  if (!accountId) return;
  clearedAccounts.add(accountId);
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(PREFIX + accountId + ":")) localStorage.removeItem(key);
    }
  } catch {
    /* Logging out must work without browser storage. */
  }
}
