"use client";
import { use } from "react";
import { PlatformConsole } from "@/features/platform-console";
export default function Page({params}:{params:Promise<{area:string}>}) {
  const {area}=use(params);
  return <PlatformConsole area={area}/>;
}
