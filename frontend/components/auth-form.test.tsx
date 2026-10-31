import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
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
});
