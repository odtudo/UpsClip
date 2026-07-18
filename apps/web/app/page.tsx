import Link from "next/link";
import { Icon } from "@/components/ui/icons";

const workflows = [
  {
    href: "/vertical/new",
    title: "Vertical Clip",
    description: "Create a short-form video from a specific VOD interval.",
    steps: "Source · Preview · Edit · Render",
    icon: "vertical" as const,
    accent: "text-blue-400 bg-blue-500/10",
  },
  {
    href: "/long-form/new",
    title: "Long-form Clip",
    description:
      "Analyze a VOD and discover conversation-based video candidates.",
    steps: "Analyze · Select · Preview · Edit",
    icon: "longform" as const,
    accent: "text-emerald-400 bg-emerald-500/10",
  },
];

export default function HomePage() {
  return (
    <div className="py-6">
      <div className="max-w-2xl">
        <p className="eyebrow">Clipping Studio</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">
          Create and publish clips from Twitch VODs.
        </h1>
        <p className="mt-4 text-lg leading-8 text-secondary">
          Choose a focused workflow. Review the raw interval first, then apply
          edits and publish only after checking the final render.
        </p>
      </div>
      <section
        className="mt-10 grid gap-5 md:grid-cols-2"
        aria-label="Create a clip"
      >
        {workflows.map((workflow) => (
          <Link
            key={workflow.href}
            href={workflow.href}
            className="group surface p-6 transition hover:-translate-y-0.5 hover:border-secondary"
          >
            <div
              className={`grid h-11 w-11 place-items-center rounded-md ${workflow.accent}`}
            >
              <Icon name={workflow.icon} className="h-6 w-6" />
            </div>
            <h2 className="mt-6 text-xl font-semibold">{workflow.title}</h2>
            <p className="mt-2 leading-6 text-secondary">
              {workflow.description}
            </p>
            <p className="mt-5 text-xs font-medium uppercase tracking-wider text-muted">
              {workflow.steps}
            </p>
            <span className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-accentSoft">
              Start workflow{" "}
              <span
                aria-hidden="true"
                className="transition group-hover:translate-x-1"
              >
                →
              </span>
            </span>
          </Link>
        ))}
      </section>
      <section className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6">
        <div>
          <h2 className="font-semibold">Continue existing work</h2>
          <p className="mt-1 text-sm text-secondary">
            Analyses and renders are persisted by the local backend.
          </p>
        </div>
        <Link href="/jobs" className="button-secondary">
          Open Jobs
        </Link>
      </section>
    </div>
  );
}
