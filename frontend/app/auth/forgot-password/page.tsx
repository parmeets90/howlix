import { Suspense } from "react";
import { AuthForm } from "@/components/auth-form";

export default function ForgotPasswordPage() {
  return <Suspense><AuthForm mode="forgot" /></Suspense>;
}
