import type { Metadata } from "next";
import "geist/font/sans";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Howlix — Find the moments worth watching",
    template: "%s — Howlix",
  },
  description: "An AI-powered workspace for finding the strongest moments in long-form video.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark" data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}

