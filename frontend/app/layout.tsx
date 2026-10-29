import type { Metadata, Viewport } from "next";
import "geist/font/sans";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://howlix.wolvesgang.digital"),
  applicationName: "Howlix",
  title: {
    default: "Howlix — Find the moments worth watching",
    template: "%s — Howlix",
  },
  description: "An AI-powered workspace for finding the strongest moments in long-form video.",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/brand/howlix-icon-192.png", type: "image/png", sizes: "192x192" },
    ],
    shortcut: "/favicon.ico",
    apple: [{ url: "/brand/howlix-app-180.png", type: "image/png", sizes: "180x180" }],
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Howlix",
  },
  openGraph: {
    type: "website",
    url: "/",
    siteName: "Howlix",
    title: "Howlix — Find the moments worth watching",
    description: "AI-powered video clipping by Wolvesgang Digital.",
    images: [
      {
        url: "/brand/howlix-social-banner-1200x630.png",
        width: 1200,
        height: 630,
        alt: "Howlix — Find the moments worth watching",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Howlix — Find the moments worth watching",
    description: "AI-powered video clipping by Wolvesgang Digital.",
    images: ["/brand/howlix-social-banner-1200x630.png"],
  },
};

export const viewport: Viewport = {
  colorScheme: "dark",
  themeColor: "#0F0B1D",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark" data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}

