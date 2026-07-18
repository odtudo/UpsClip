import type { SVGProps } from "react";

export function Icon({
  name,
  ...props
}: SVGProps<SVGSVGElement> & {
  name:
    | "home"
    | "jobs"
    | "settings"
    | "vertical"
    | "longform"
    | "video"
    | "upload"
    | "check"
    | "menu";
}) {
  const paths: Record<typeof name, React.ReactNode> = {
    home: (
      <>
        <path d="m3 11 9-8 9 8" />
        <path d="M5 10v10h14V10" />
      </>
    ),
    jobs: (
      <>
        <rect x="3" y="5" width="18" height="15" rx="2" />
        <path d="M8 5V3h8v2M8 10h8M8 14h5" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1V21H9.6v-.09a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1-.4H3V9.6h.09a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1V3h4v.09a1.7 1.7 0 0 0 1.1 1.5 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.13.37.34.7.6 1 .3.27.65.4 1 .4h.09v4H21c-.35 0-.7.13-1 .4-.26.3-.47.63-.6 1Z" />
      </>
    ),
    vertical: (
      <>
        <rect x="7" y="2" width="10" height="20" rx="2" />
        <path d="M10 18h4" />
      </>
    ),
    longform: (
      <>
        <rect x="2" y="5" width="20" height="14" rx="2" />
        <path d="m10 9 5 3-5 3Z" />
      </>
    ),
    video: (
      <>
        <rect x="3" y="5" width="14" height="14" rx="2" />
        <path d="m17 10 4-2v8l-4-2" />
      </>
    ),
    upload: (
      <>
        <path d="M12 16V3m0 0L7 8m5-5 5 5" />
        <path d="M4 15v5h16v-5" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  };
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
