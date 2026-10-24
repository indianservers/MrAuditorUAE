import type { Metadata } from "next";
import { ClientShare } from "@/features/client-share";
export const metadata: Metadata = {
  title: "Mr Auditor • Client document request",
  referrer: "no-referrer",
  robots: { index: false, follow: false },
};
export default async function Page({
  params,
}: {
  params: Promise<{ tenant: string; link: string }>;
}) {
  const { tenant, link } = await params;
  return <ClientShare tenant={tenant} link={link} />;
}
