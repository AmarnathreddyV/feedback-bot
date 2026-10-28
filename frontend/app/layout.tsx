import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Niloufer | Customer Experience Intelligence",
  description: "Customer feedback and complaint analytics portal"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
