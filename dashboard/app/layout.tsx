import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { DaemonBanner } from "@/components/DaemonBanner";
import { CommandPalette } from "@/components/CommandPalette";
import { DaemonProvider } from "@/lib/daemon";

export const metadata: Metadata = {
  title: "Iron Jarvis — Control Center",
  description: "Dashboard for the Iron Jarvis daemon.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <DaemonProvider>
          <div className="flex h-screen flex-col overflow-hidden">
            {/* App-wide daemon-offline banner (shared /health source). */}
            <DaemonBanner />
            <div className="relative flex flex-1 overflow-hidden">
              {/* Ambient arc-reactor glow behind everything. */}
              <div className="app-aura pointer-events-none absolute inset-0 -z-10" />
              <Sidebar />
              <main className="flex-1 overflow-y-auto">
                <div className="mx-auto max-w-7xl px-6 py-8 lg:px-10">{children}</div>
              </main>
            </div>
          </div>
          {/* ⌘K command palette — navigate, new session, connect a model. */}
          <CommandPalette />
        </DaemonProvider>
      </body>
    </html>
  );
}
