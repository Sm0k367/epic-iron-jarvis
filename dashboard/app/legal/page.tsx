"use client";

import Link from "next/link";
import {
  Scale,
  Shield,
  FileText,
  Cookie,
  CreditCard,
  Ban,
  Copyright,
  BookOpen,
  Mail,
  ScrollText,
  ArrowRight,
} from "lucide-react";
import { LegalDocument } from "@/components/LegalDocument";
import { COMPANY } from "@/lib/company";

const DOCS = [
  {
    href: "/legal/privacy",
    title: "Privacy Policy",
    desc: "Local-first data handling, third-party providers, your choices.",
    icon: Shield,
    md: "/legal/PRIVACY.md",
  },
  {
    href: "/legal/terms",
    title: "Terms of Service",
    desc: "License, disclaimers, liability limits, AI output responsibility.",
    icon: FileText,
    md: "/legal/TERMS.md",
  },
  {
    href: "/legal/acceptable-use",
    title: "Acceptable Use",
    desc: "What you may and may not do with agents, channels, and APIs.",
    icon: Ban,
    md: "/legal/ACCEPTABLE-USE.md",
  },
  {
    href: "/legal/billing",
    title: "Billing & Refunds",
    desc: "Credits, Stripe checkout, refunds, free local use.",
    icon: CreditCard,
    md: "/legal/BILLING.md",
  },
  {
    href: "/legal/cookies",
    title: "Cookies & Storage",
    desc: "localStorage, functional preferences, no ad trackers by default.",
    icon: Cookie,
    md: "/legal/COOKIES.md",
  },
  {
    href: "/legal/security",
    title: "Security Policy",
    desc: "Vulnerability reporting, hardening checklist, safe harbor.",
    icon: Shield,
    md: "/legal/SECURITY.md",
  },
  {
    href: "/legal/copyright",
    title: "Copyright & DMCA",
    desc: "Ownership, trademarks, takedown notices.",
    icon: Copyright,
    md: "/legal/COPYRIGHT.md",
  },
  {
    href: "/legal/whitepaper",
    title: "Product Whitepaper",
    desc: "Architecture, trust model, data flows, roadmap themes.",
    icon: BookOpen,
    md: "/legal/WHITEPAPER.md",
  },
  {
    href: "/legal/contact",
    title: "Contact",
    desc: "Email, X, GitHub — how to reach Epic Tech AI.",
    icon: Mail,
    md: "/legal/CONTACT.md",
  },
  {
    href: "/legal/license",
    title: "License",
    desc: "Proprietary notice and use permissions.",
    icon: ScrollText,
    md: "/legal/LICENSE.txt",
  },
];

export default function LegalIndexPage() {
  return (
    <LegalDocument
      title="Legal & whitepages"
      subtitle={`Policies for ${COMPANY.product}. Effective ${COMPANY.effectiveDate}.`}
    >
      <p>
        These documents apply to Epic Tech AI software, documentation, and optional
        commerce features. They are also published in the repository under{" "}
        <code className="rounded bg-white/5 px-1 text-zinc-300">legal/</code>.
      </p>
      <p className="text-xs text-zinc-600">
        Not personalized legal advice. For formal counsel, consult a licensed attorney
        in your jurisdiction.
      </p>

      <div className="!mt-8 grid gap-3 sm:grid-cols-2">
        {DOCS.map((doc) => {
          const Icon = doc.icon;
          return (
            <Link
              key={doc.href}
              href={doc.href}
              className="group flex flex-col gap-2 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 transition hover:border-accent/30 hover:bg-accent/[0.04]"
            >
              <div className="flex items-center justify-between">
                <span className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 text-accent-soft">
                  <Icon size={18} />
                </span>
                <ArrowRight
                  size={14}
                  className="text-zinc-600 transition group-hover:text-accent-soft"
                />
              </div>
              <div className="text-sm font-semibold text-zinc-100">{doc.title}</div>
              <p className="text-[13px] leading-relaxed text-zinc-500">{doc.desc}</p>
              <span className="text-[11px] text-zinc-600">Source: {doc.md}</span>
            </Link>
          );
        })}
      </div>

      <section className="!mt-10">
        <h2>Quick contact</h2>
        <p>
          <a href={COMPANY.emailHref}>{COMPANY.email}</a>
          {" · "}
          <a href={COMPANY.x.url} target="_blank" rel="noreferrer">
            {COMPANY.x.handle}
          </a>
          {" · "}
          <a href={COMPANY.github.url} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </p>
        <p className="flex items-center gap-2 text-xs text-zinc-600">
          <Scale size={12} />
          Security reports: email subject <strong className="text-zinc-400">SECURITY</strong>{" "}
          — do not open public issues for unpatched critical vulns.
        </p>
      </section>
    </LegalDocument>
  );
}
