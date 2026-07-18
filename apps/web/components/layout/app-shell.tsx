"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getSetupStatus, type SetupStatus } from "@/lib/api";
import { Icon } from "@/components/ui/icons";

const navigation = [
  { href: "/", label: "Home", icon: "home" as const },
  { href: "/jobs", label: "Jobs", icon: "jobs" as const },
  { href: "/settings", label: "Settings", icon: "settings" as const },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  useEffect(() => {
    void getSetupStatus()
      .then(setSetup)
      .catch(() => setSetup(null));
  }, []);
  return (
    <div className="min-h-screen bg-canvas text-primary">
      <button
        aria-label="Open navigation"
        onClick={() => setOpen(true)}
        className="fixed left-4 top-4 z-50 rounded-md border border-line bg-panel p-2 text-secondary lg:hidden"
      >
        <Icon name="menu" className="h-5 w-5" />
      </button>
      {open && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-line bg-elevated transition-transform lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        <Link
          href="/"
          className="flex h-16 items-center gap-3 border-b border-line px-5"
        >
          <span className="grid h-8 w-8 place-items-center rounded-md bg-accent font-bold text-white">
            C
          </span>
          <span className="font-semibold tracking-tight">Clipping Studio</span>
        </Link>
        <nav className="space-y-1 p-3" aria-label="Primary navigation">
          {navigation.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium ${active ? "bg-active text-primary" : "text-secondary hover:bg-card hover:text-primary"}`}
              >
                <Icon name={item.icon} className="h-5 w-5" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto border-t border-line p-4 text-xs text-muted">
          <div className="flex items-center justify-between">
            <span>API</span>
            <span
              className={`flex items-center gap-1.5 ${setup ? "text-success" : "text-warning"}`}
            >
              <i
                className={`h-1.5 w-1.5 rounded-full ${setup ? "bg-success" : "bg-warning"}`}
              />
              {setup ? "Healthy" : "Unavailable"}
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span>YouTube</span>
            <span
              className={setup?.youtube_ready ? "text-success" : "text-warning"}
            >
              {setup?.youtube_ready ? "Connected" : "Disconnected"}
            </span>
          </div>
          <Link
            href="/inspector"
            className="mt-4 block text-muted hover:text-secondary"
          >
            Engineering: VOD Inspector
          </Link>
        </div>
      </aside>
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center border-b border-line bg-canvas/95 px-5 backdrop-blur lg:px-8">
          <div className="ml-11 text-sm text-secondary lg:ml-0">
            {pathname === "/"
              ? "Workspace"
              : pathname
                  .split("/")
                  .filter(Boolean)
                  .map((part) => part.replaceAll("-", " "))
                  .join(" / ")}
          </div>
          <div className="ml-auto flex items-center gap-3 text-xs text-muted">
            <span className="hidden sm:inline">Local workspace</span>
            <span className="h-2 w-2 rounded-full bg-success" />
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-5 py-8 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
