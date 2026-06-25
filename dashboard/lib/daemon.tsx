"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError, get } from "./api";
import type { Health } from "./types";

export interface DaemonState {
  /** True once a /health poll has succeeded; false when the daemon is offline. */
  online: boolean;
  /** Latest /health payload, or null before the first successful poll. */
  health: Health | null;
  /** True until the first poll resolves (so we don't flash "offline" on load). */
  checking: boolean;
  /** Force an immediate re-poll. */
  refresh: () => void;
}

const DaemonContext = createContext<DaemonState | null>(null);

/**
 * One shared `/health` poll for the whole app. The offline banner and the
 * sidebar status dot both read from this so they never disagree.
 */
export function DaemonProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [online, setOnline] = useState(false);
  const [checking, setChecking] = useState(true);
  const [nonce, setNonce] = useState(0);
  const firstRef = useRef(true);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const h = await get<Health>("/health");
        if (cancelled) return;
        setHealth(h);
        setOnline(true);
      } catch (err) {
        if (cancelled) return;
        // status 0 === network error === daemon unreachable.
        if (err instanceof ApiError && err.status === 0) {
          setOnline(false);
        } else {
          // Reachable but erroring — still "online" enough to not show the banner.
          setOnline(true);
        }
      } finally {
        if (!cancelled && firstRef.current) {
          firstRef.current = false;
          setChecking(false);
        }
      }
    };

    poll();
    const id = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [nonce]);

  return (
    <DaemonContext.Provider value={{ online, health, checking, refresh }}>
      {children}
    </DaemonContext.Provider>
  );
}

export function useDaemon(): DaemonState {
  const ctx = useContext(DaemonContext);
  if (ctx === null) {
    // Safe fallback if a component renders outside the provider.
    return { online: true, health: null, checking: true, refresh: () => {} };
  }
  return ctx;
}
