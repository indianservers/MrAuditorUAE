import { Providers } from "@/components/providers";
import "@/styles/globals.css";
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "AuditOS UAE | Financial Intelligence",
  description: "Secure audit and accounting workbench",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
