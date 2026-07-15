import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Twitch VOD Clip Editor",
  description: "Local Twitch VOD trimming, editing, preview, and YouTube upload",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

