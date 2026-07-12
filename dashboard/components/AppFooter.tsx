"use client";

import Link from "next/link";
import { COMPANY } from "@/lib/company";

/** Slim legal strip — privacy / terms / contact always one click away. */
export function AppFooter() {
  return (
    <footer className="mt-10 border-t border-white/[0.06] pt-6 pb-2 text-[11px] text-zinc-600">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p>
          {COMPANY.copyright} ·{" "}
          <a href={COMPANY.emailHref} className="hover:text-zinc-400">
            {COMPANY.email}
          </a>{" "}
          ·{" "}
          <a
            href={COMPANY.x.url}
            target="_blank"
            rel="noreferrer"
            className="hover:text-zinc-400"
          >
            {COMPANY.x.handle}
          </a>
        </p>
        <nav className="flex flex-wrap gap-x-3 gap-y-1">
          <Link href="/legal" className="hover:text-accent-soft">
            Legal
          </Link>
          <Link href="/legal/privacy" className="hover:text-accent-soft">
            Privacy
          </Link>
          <Link href="/legal/terms" className="hover:text-accent-soft">
            Terms
          </Link>
          <Link href="/legal/billing" className="hover:text-accent-soft">
            Billing
          </Link>
          <Link href="/legal/security" className="hover:text-accent-soft">
            Security
          </Link>
          <Link href="/legal/contact" className="hover:text-accent-soft">
            Contact
          </Link>
        </nav>
      </div>
    </footer>
  );
}
