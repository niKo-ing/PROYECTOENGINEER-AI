"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

const STORAGE_KEY = "solotodo_compare_ids";
const MAX_COMPARE = 4;

type Listener = () => void;

const listeners = new Set<Listener>();
let cached: number[] | null = null;

function parseStored(): number[] {
  if (typeof window === "undefined") return [];
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return [];
    const parsed: unknown = JSON.parse(stored);
    if (Array.isArray(parsed)) {
      return parsed.filter((item): item is number => Number.isInteger(item) && item > 0).slice(0, MAX_COMPARE);
    }
    return [];
  } catch {
    return [];
  }
}

function readSnapshot(): number[] {
  if (cached === null) cached = parseStored();
  return cached;
}

const EMPTY_SNAPSHOT: number[] = [];

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) {
      cached = null;
      listener();
    }
  };
  if (typeof window !== "undefined") {
    window.addEventListener("storage", onStorage);
  }
  return () => {
    listeners.delete(listener);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", onStorage);
    }
  };
}

function emitChange() {
  for (const listener of listeners) listener();
}

function write(next: number[]) {
  cached = next;
  try {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    }
  } catch {
    // storage unavailable; keep in-memory snapshot
  }
  emitChange();
}

export interface CompareContextValue {
  ids: number[];
  selected: Set<number>;
  isSelected: (id: number) => boolean;
  toggle: (id: number) => void;
  clear: () => void;
  remove: (id: number) => void;
}

const CompareContext = createContext<CompareContextValue | null>(null);

export function CompareProvider({ children }: { children: ReactNode }) {
  const ids = useSyncExternalStore(subscribe, readSnapshot, () => EMPTY_SNAPSHOT);

  const toggle = useCallback((id: number) => {
    const previous = readSnapshot();
    if (previous.includes(id)) {
      write(previous.filter((item) => item !== id));
      return;
    }
    const next = previous.length >= MAX_COMPARE ? [...previous.slice(1), id] : [...previous, id];
    write(next);
  }, []);

  const clear = useCallback(() => write([]), []);

  const remove = useCallback((id: number) => {
    write(readSnapshot().filter((item) => item !== id));
  }, []);

  const value = useMemo<CompareContextValue>(
    () => ({
      ids,
      selected: new Set(ids),
      isSelected: (id) => ids.includes(id),
      toggle,
      clear,
      remove,
    }),
    [ids, toggle, clear, remove]
  );

  return <CompareContext.Provider value={value}>{children}</CompareContext.Provider>;
}

export function useCompare(): CompareContextValue {
  const context = useContext(CompareContext);
  if (!context) {
    throw new Error("useCompare debe usarse dentro de CompareProvider");
  }
  return context;
}