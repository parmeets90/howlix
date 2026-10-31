import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ authenticated: false }));
vi.mock("@supabase/ssr", () => ({
  createServerClient: () => ({
    auth: {
      getClaims: async () => ({
        data: state.authenticated ? { claims: { sub: "user-a" } } : null,
      }),
    },
  }),
}));

import { updateSession } from "./proxy";


describe("authenticated navigation", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test";
    state.authenticated = false;
  });

  it("redirects anonymous dashboard requests to login", async () => {
    const response = await updateSession(new NextRequest("http://localhost:3000/dashboard/projects/one"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toContain("/auth/login?next=%2Fdashboard%2Fprojects%2Fone");
  });

  it("redirects an authenticated user away from login", async () => {
    state.authenticated = true;
    const response = await updateSession(new NextRequest("http://localhost:3000/auth/login"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });
});
