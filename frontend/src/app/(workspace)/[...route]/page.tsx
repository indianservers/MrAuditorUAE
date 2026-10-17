import { Workbench } from "@/features/workbench";
export default async function Page({
  params,
}: {
  params: Promise<{ route: string[] }>;
}) {
  const { route } = await params;
  return <Workbench route={"/" + route.join("/")} />;
}
