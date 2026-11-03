import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

let searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => searchParams,
}));
vi.mock("@/lib/supabase/client", () => ({ createClient: vi.fn() }));

import { AuthForm } from "./auth-form";


describe("private beta authentication", () => {
  it("renders login navigation and password recovery", () => {
    const markup = renderToStaticMarkup(<AuthForm mode="login" />);
    expect(markup).toContain("Welcome back");
    expect(markup).toContain("Continue with Google");
    expect(markup).toContain("/auth/forgot-password");
    expect(markup).toContain("/auth/signup");
  });

  it("renders email verification guidance for signup", () => {
    const markup = renderToStaticMarkup(<AuthForm mode="signup" />);
    expect(markup).toContain("Create your account");
    expect(markup).toContain("Create account");
    expect(markup).toContain("Continue with Google");
    expect(markup).toContain('minLength="8"');
  });

  it("treats an already-used confirmation link as a helpful notice", () => {
    searchParams = new URLSearchParams("notice=confirmation");
    const markup = renderToStaticMarkup(<AuthForm mode="login" />);
    expect(markup).toContain("Your email may already be verified");
    expect(markup).not.toContain("invalid or has expired");
    searchParams = new URLSearchParams();
  });
});
