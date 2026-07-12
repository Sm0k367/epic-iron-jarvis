"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { LegalDocument } from "@/components/LegalDocument";
import { SkeletonRows, ErrorNote } from "@/components/ui";

export function MarkdownLegalPage({
  title,
  mdUrl,
  subtitle,
}: {
  title: string;
  mdUrl: string;
  subtitle?: string;
}) {
  const [md, setMd] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setMd(null);
    setErr(null);
    fetch(mdUrl)
      .then(async (r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.text();
      })
      .then((t) => {
        if (!cancelled) setMd(t);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [mdUrl]);

  return (
    <LegalDocument title={title} subtitle={subtitle} mdPath={mdUrl}>
      {err && <ErrorNote>{err}</ErrorNote>}
      {!md && !err && <SkeletonRows rows={8} />}
      {md && (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{md}</ReactMarkdown>
      )}
    </LegalDocument>
  );
}
