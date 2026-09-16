import { LockedFeature } from "@/components/locked-feature";
import { LoginForm } from "@/components/login-form";

export default function LoginPage() {
  // Locked for the Assignment 4 submission deployment -- see farm/page.tsx.
  if (process.env.LOCK_FARM_FEATURES === "true") {
    return <LockedFeature title="Sign in" />;
  }
  return (
    <div className="flex min-h-dvh items-center justify-center bg-background px-4">
      <LoginForm />
    </div>
  );
}
