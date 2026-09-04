import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AppProviders } from "@/components/app-providers";

export const metadata: Metadata = {
  metadataBase: new URL("http://localhost:3000"),
  applicationName: "Socium",
  title: "Socium — Local-First AI Business OS",
  description: "Private AI business operations for content, approvals, leads, outreach, and growth.",
  openGraph: {
    title: "Socium — Local-First AI Business OS",
    description: "Private AI business operations for content, approvals, leads, outreach, and growth.",
    type: "website",
    images: [
      {
        url: "/brand/socium-og-image-1200x630.png",
        width: 1200,
        height: 630,
        alt: "Socium — Local-First AI Business OS",
      },
    ],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "dark",
  themeColor: "#09090b",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark font-sans" suppressHydrationWarning>
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
