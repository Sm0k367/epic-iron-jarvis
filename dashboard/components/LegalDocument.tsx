"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft, Scale } from "lucide-react";
import { PageShell, Reveal } from "@/components/motion";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui";
import { COMPANY } from "@/lib/company";

const NAV = [
  { href: "/legal", label: "Index" },
  { href: "/legal/privacy", label: "Privacy" },
  { href: "/legal/terms", label: "Terms" },
  { href: "/legal/acceptable-use", label: "AUP" },
  { href: "/legal/billing", label: "Billing" },
  { href: "/legal/cookies", label: "Cookies" },
  { href: "/legal/security", label: "Security" },
  { href: "/legal/copyright", label: "Copyright" },
  { href: "/legal/whitepaper", label: "Whitepaper" },
  { href: "/legal/contact", label: "Contact" },
  { href: "/legal/license", label: "License" },
];

export function LegalDocument({
  title,
  subtitle,
  children,
  mdPath,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  /** Path under /legal/*.md served from public/ */
  mdPath?: string;
}) {
  return (
    <PageShell>
      <PageHeader
        title={title}
        subtitle={
          subtitle ??
          `${COMPANY.name} · Effective ${COMPANY.effectiveDate} · ${COMPANY.email}`
        }
        actions={
          <Link
            href="/legal"
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-100"
          >
            <ArrowLeft size={14} /> All legal
          </Link>
        }
      />

      <Reveal>
        <nav className="mb-6 flex flex-wrap gap-2">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-full border border-white/[0.08] bg-white/[0.02] px-3 py-1 text-[11px] font-medium text-zinc-400 hover:border-accent/30 hover:text-accent-soft"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </Reveal>

      <Reveal>
        <Card className="prose-legal space-y-6 p-6 text-sm leading-relaxed text-zinc-400 sm:p-8">
          <div className="flex items-center gap-2 text-accent-soft">
            <Scale size={16} />
            <span className="text-xs font-semibold uppercase tracking-[0.14em]">
              {COMPANY.product} Legal
            </span>
          </div>
          <div className="space-y-5 [&_a]:text-accent-soft [&_a]:hover:text-accent [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-zinc-100 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-zinc-200 [&_li]:ml-4 [&_li]:list-disc [&_p]:text-zinc-400 [&_strong]:text-zinc-200 [&_table]:w-full [&_table]:text-left [&_td]:border-t [&_td]:border-white/5 [&_td]:py-2 [&_td]:pr-3 [&_th]:py-2 [&_th]:pr-3 [&_th]:text-zinc-500">
            {children}
          </div>
          {mdPath && (
            <p className="border-t border-white/10 pt-4 text-xs text-zinc-600">
              Source markdown:{" "}
              <a href={mdPath} target="_blank" rel="noreferrer" className="text-accent-soft">
                {mdPath}
              </a>{" "}
              · Repo:{" "}
              <a href={COMPANY.github.url} target="_blank" rel="noreferrer">
                {COMPANY.github.repo}
              </a>
            </p>
          )}
          <p className="text-xs text-zinc-600">
            {COMPANY.copyright} ·{" "}
            <a href={COMPANY.emailHref}>{COMPANY.email}</a> ·{" "}
            <a href={COMPANY.x.url} target="_blank" rel="noreferrer">
              {COMPANY.x.handle}
            </a>
          </p>
        </Card>
      </Reveal>
    </PageShell>
  );
}
