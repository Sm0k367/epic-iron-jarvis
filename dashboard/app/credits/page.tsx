"use client";

import { useState } from "react";
import Link from "next/link";
import { Coins, CreditCard, ShoppingCart, Gauge, Shield } from "lucide-react";
import { post, ApiError } from "@/lib/api";
import { useApi, usePolledApi } from "@/lib/useApi";
import {
  Card,
  Stat,
  OfflineHint,
  Empty,
  SkeletonRows,
  ErrorNote,
  SuccessNote,
  LoaderInline,
} from "@/components/ui";
import { PageHeader } from "@/components/PageHeader";
import { PageShell, Reveal } from "@/components/motion";

interface BudgetLimits {
  max_tokens_per_day: number;
  max_usd_per_day: number;
  max_runs_per_hour: number;
  max_tokens_per_run: number;
}

interface BudgetRemaining {
  tokens_24h: number | null;
  usd_24h: number | null;
  runs_1h: number | null;
}

interface BillingSummary {
  enabled: boolean;
  require_credits: boolean;
  min_credits: number;
  currency: string;
  balance: number;
  wallet_id: string;
  stripe_configured: boolean;
  products: {
    id: string;
    name: string;
    credits: number;
    price_cents: number;
    stripe_price_configured: boolean;
  }[];
  budgets?: {
    stats: {
      tokens_24h: number;
      usd_24h: number;
      credits_burned_24h: number;
      runs_1h: number;
      runs_24h: number;
    };
    limits: BudgetLimits;
    remaining: BudgetRemaining;
  };
}

interface LedgerEntry {
  id: string;
  kind: string;
  amount: number;
  balance_after: number;
  ref_type: string;
  ref_id: string;
  created_at: string | null;
}

/**
 * Operational credits console. Secrets never collected here —
 * Stripe keys live in env/vault only.
 */
export default function CreditsPage() {
  const { data, error, loading, reload } = usePolledApi<BillingSummary>("/billing", 15000);
  const { data: ledgerData, reload: reloadLedger } = useApi<{ entries: LedgerEntry[] }>(
    "/billing/ledger?limit=40",
  );
  const offline = error && error.status === 0;
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [grantAmt, setGrantAmt] = useState("100");

  async function buy(productId: string) {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await post<{ checkout_url?: string; purchase_id?: string }>(
        "/billing/checkout",
        { product_id: productId },
      );
      if (res.checkout_url) {
        window.open(res.checkout_url, "_blank", "noopener,noreferrer");
        setMsg("Opened Stripe Checkout in a new tab.");
      } else {
        setMsg(`Checkout created: ${res.purchase_id ?? "ok"}`);
      }
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function grant() {
    const amount = parseFloat(grantAmt);
    if (!Number.isFinite(amount) || amount <= 0) {
      setErr("Enter a positive credit amount.");
      return;
    }
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await post<{ balance: number }>("/billing/grant", {
        amount,
        reason: "dashboard_grant",
      });
      setMsg(`Granted ${amount} credits. Balance: ${res.balance}`);
      reload();
      reloadLedger();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const budgets = data?.budgets;
  const stats = budgets?.stats;

  return (
    <PageShell>
      <PageHeader
        title="Credits & budgets"
        subtitle="SOTA spend control — prepaid credits, rolling token budgets, Stripe packs. Keys never leave the vault."
      />

      {offline && <OfflineHint />}
      {err && <ErrorNote>{err}</ErrorNote>}
      {msg && <SuccessNote>{msg}</SuccessNote>}

      {loading && !data ? (
        <SkeletonRows rows={5} />
      ) : !data ? (
        <Empty title="Billing offline" body="Start the daemon to manage credits." />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Reveal>
            <Card className="space-y-4 p-6">
              <div className="flex items-center gap-3">
                <Coins className="h-6 w-6 text-accent" />
                <div>
                  <p className="text-sm text-white/50">Balance</p>
                  <p className="text-3xl font-semibold text-white">
                    {data.balance.toFixed(2)}{" "}
                    <span className="text-base font-normal text-white/50">
                      {data.currency}
                    </span>
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Stat label="Billing" value={data.enabled ? "on" : "off"} />
                <Stat
                  label="Require credits"
                  value={data.require_credits ? "yes" : "no"}
                />
                <Stat label="Min to start" value={String(data.min_credits)} />
                <Stat
                  label="Stripe"
                  value={data.stripe_configured ? "ready" : "not set"}
                />
              </div>
              <div className="flex flex-wrap items-end gap-2 border-t border-white/10 pt-4">
                <label className="text-xs text-white/50">
                  Dev grant (no Stripe)
                  <input
                    className="mt-1 block w-28 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white"
                    value={grantAmt}
                    onChange={(e) => setGrantAmt(e.target.value)}
                  />
                </label>
                <button
                  type="button"
                  disabled={busy}
                  onClick={grant}
                  className="rounded-lg bg-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/15 disabled:opacity-50"
                >
                  {busy ? <LoaderInline /> : "Grant credits"}
                </button>
              </div>
              <p className="text-xs text-white/40">
                Never paste API keys here. Put Stripe keys in environment variables or
                Secrets.{" "}
                <Link href="/legal/billing" className="text-accent-soft hover:underline">
                  Billing policy
                </Link>
              </p>
            </Card>
          </Reveal>

          <Reveal>
            <Card className="space-y-4 p-6">
              <div className="flex items-center gap-2 text-white">
                <Gauge className="h-5 w-5 text-accent" />
                <h2 className="font-semibold">Rolling budgets (24h / 1h)</h2>
              </div>
              {stats ? (
                <div className="grid grid-cols-2 gap-3">
                  <Stat label="Tokens 24h" value={stats.tokens_24h.toLocaleString()} />
                  <Stat label="USD 24h (est.)" value={`$${stats.usd_24h.toFixed(4)}`} />
                  <Stat
                    label="Credits burned 24h"
                    value={stats.credits_burned_24h.toFixed(2)}
                  />
                  <Stat label="Runs 1h" value={String(stats.runs_1h)} />
                </div>
              ) : (
                <p className="text-sm text-white/40">No budget telemetry yet.</p>
              )}
              {budgets?.remaining && (
                <ul className="space-y-1 text-xs text-white/50">
                  <li>
                    Remaining tokens/day:{" "}
                    {budgets.remaining.tokens_24h == null
                      ? "unlimited"
                      : budgets.remaining.tokens_24h.toLocaleString()}
                  </li>
                  <li>
                    Remaining $/day:{" "}
                    {budgets.remaining.usd_24h == null
                      ? "unlimited"
                      : `$${budgets.remaining.usd_24h.toFixed(4)}`}
                  </li>
                  <li>
                    Remaining runs/hour:{" "}
                    {budgets.remaining.runs_1h == null
                      ? "unlimited"
                      : budgets.remaining.runs_1h}
                  </li>
                </ul>
              )}
              <p className="text-xs text-white/40">
                Configure limits under{" "}
                <Link href="/settings" className="text-accent-soft hover:underline">
                  Settings → budgets / commerce
                </Link>
                .
              </p>
            </Card>
          </Reveal>

          <Reveal>
            <Card className="space-y-3 p-6">
              <div className="mb-2 flex items-center gap-2 text-white">
                <ShoppingCart className="h-5 w-5 text-accent" />
                <h2 className="font-semibold">Credit packs</h2>
              </div>
              {(data.products ?? []).map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between rounded-xl border border-white/10 bg-black/20 px-4 py-3"
                >
                  <div>
                    <p className="font-medium text-white">{p.name}</p>
                    <p className="text-xs text-white/50">
                      {p.credits} credits · ${(p.price_cents / 100).toFixed(2)}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={busy || !data.stripe_configured}
                    onClick={() => buy(p.id)}
                    className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-40"
                  >
                    Buy
                  </button>
                </div>
              ))}
              {!data.stripe_configured && (
                <p className="flex items-start gap-2 text-xs text-amber-200/80">
                  <Shield size={14} className="mt-0.5 shrink-0" />
                  Set STRIPE_SECRET_KEY in env or vault to enable checkout. Local
                  grants still work.
                </p>
              )}
            </Card>
          </Reveal>

          <Reveal>
            <Card className="p-6">
              <div className="mb-3 flex items-center gap-2">
                <CreditCard className="h-5 w-5 text-accent" />
                <h2 className="font-semibold text-white">Ledger</h2>
              </div>
              {(ledgerData?.entries ?? []).length === 0 ? (
                <Empty title="No ledger entries yet" body="Grants and burns appear here." />
              ) : (
                <div className="max-h-80 overflow-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-white/40">
                      <tr>
                        <th className="py-2 pr-3">When</th>
                        <th className="py-2 pr-3">Kind</th>
                        <th className="py-2 pr-3">Amt</th>
                        <th className="py-2">Bal</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(ledgerData?.entries ?? []).map((e) => (
                        <tr key={e.id} className="border-t border-white/5 text-white/80">
                          <td className="py-2 pr-3 text-[11px] text-white/40">
                            {(e.created_at ?? "—").slice(0, 19)}
                          </td>
                          <td className="py-2 pr-3">{e.kind}</td>
                          <td className="py-2 pr-3">{e.amount}</td>
                          <td className="py-2">{e.balance_after}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </Reveal>
        </div>
      )}
    </PageShell>
  );
}
