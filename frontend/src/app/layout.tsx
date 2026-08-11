import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Ripple — plans that survive reality",
  description:
    "Ripple scores how resilient your degree plan is, and reroutes it with the fewest possible changes when a course fills up.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      // Ripple is light-theme only; pin the scheme so native form controls
      // and scrollbars don't render dark against the light palette.
      style={{ colorScheme: "light" }}
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-neutral-50 text-neutral-900">
        {children}
      </body>
    </html>
  );
}
