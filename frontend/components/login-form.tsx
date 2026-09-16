"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Mail, MapPinned } from "lucide-react";

import { supabase } from "@/lib/supabase-client";
import { useSession } from "@/lib/use-session";

// Magic-link only, deliberately -- no password to set, reset, or leak, and
// Supabase's default email provider handles delivery with zero setup. A
// dedicated password flow is a Phase 5 (production hardening) question,
// not a Phase 1 one.
export function LoginForm() {
  const router = useRouter();
  const { session, loading } = useSession();
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!loading && session) {
      router.replace("/farm");
    }
  }, [loading, session, router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus("sending");
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/farm` },
    });
    if (error) {
      setErrorMessage(error.message);
      setStatus("error");
    } else {
      setStatus("sent");
    }
  }

  if (loading || session) {
    return null;
  }

  if (status === "sent") {
    return (
      <div className="flex w-full max-w-sm flex-col items-center gap-3 rounded-xl border border-accent/40 bg-card p-8 text-center shadow-sm">
        <div className="flex size-12 items-center justify-center rounded-full bg-primary/10">
          <Mail className="size-5 text-primary" aria-hidden="true" />
        </div>
        <h1 className="font-heading text-xl font-semibold text-card-foreground">Check your email</h1>
        <p className="text-sm text-muted-foreground">
          We sent a sign-in link to <span className="font-medium text-foreground">{email}</span>. Open it on this
          device to continue.
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full max-w-sm space-y-4 rounded-xl border border-accent/40 bg-card p-6 shadow-sm"
    >
      <div className="flex flex-col items-center gap-2 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-primary/10">
          <MapPinned className="size-5 text-primary" aria-hidden="true" />
        </div>
        <h1 className="font-heading text-xl font-semibold text-card-foreground">Sign in to My Farm</h1>
        <p className="text-sm text-muted-foreground">We&apos;ll email you a link -- no password needed.</p>
      </div>
      <input
        type="email"
        required
        autoFocus
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@farm.com"
        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
      />
      {status === "error" && <p className="text-sm text-destructive">{errorMessage}</p>}
      <button
        type="submit"
        disabled={status === "sending"}
        className="w-full cursor-pointer rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90 disabled:opacity-60"
      >
        {status === "sending" ? "Sending..." : "Send sign-in link"}
      </button>
    </form>
  );
}
