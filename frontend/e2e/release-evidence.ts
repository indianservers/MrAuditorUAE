import type {Page} from "@playwright/test";
import {appendFileSync} from "node:fs";
export function recordReleaseEvidence(page:Page){
  const path=process.env.AUDITOS_BROWSER_EVIDENCE;
  if(!path)return;
  page.on("framenavigated",frame=>{if(frame===page.mainFrame())appendFileSync(path,JSON.stringify({type:"navigation",path:new URL(frame.url()).pathname})+"\n");});
  page.on("response",response=>{
    const url=new URL(response.url());
    if(url.pathname.startsWith("/api/backend/"))appendFileSync(path,JSON.stringify({type:"api",path:url.pathname,method:response.request().method(),status:response.status()})+"\n");
  });
}
