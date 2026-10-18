import {test,expect} from "@playwright/test";

test("release smoke uses real BFF authentication, client writes and logout revocation",async({page})=>{
  const email=process.env.AUDITOS_SMOKE_EMAIL;
  const password=process.env.AUDITOS_SMOKE_PASSWORD;
  if(!email||!password)throw new Error("Explicit isolated smoke identity required");
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password",{exact:true}).fill(password);
  await page.getByRole("button",{name:"Sign in",exact:true}).click();
  await page.waitForURL("**/dashboard");
  const tenants=await page.request.get("/api/backend/tenants");expect(tenants.status()).toBe(200);
  const id=(await tenants.json())[0].id;
  const headers={"X-Tenant-ID":id,"Origin":new URL(page.url()).origin};
  const created=await page.request.post("/api/backend/clients",{headers,data:{code:`SMOKE${Date.now()}`,name:"Synthetic CI release client"}});
  expect(created.status()).toBe(201);
  const client=await created.json();
  const read=await page.request.get(`/api/backend/clients/${client.id}`,{headers});
  expect(read.status()).toBe(200);expect((await read.json()).name).toBe("Synthetic CI release client");
  expect((await page.request.get("/api/backend/platform/tenants")).status()).toBe(403);
  expect((await page.request.delete("/api/session",{headers:{Origin:new URL(page.url()).origin}})).status()).toBe(204);
  expect((await page.request.get("/api/session")).status()).toBe(401);
});
