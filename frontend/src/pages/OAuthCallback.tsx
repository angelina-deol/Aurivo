import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useAuthStore } from "@/hooks/useAuthStore";

/**
 * Lands here after Google OAuth completes. The backend redirects with
 * tokens in the URL fragment (#access_token=...&refresh_token=...) rather
 * than query params, since fragments never reach the server on the next
 * request or leak via Referer headers. window.location.hash is what we
 * read, not useSearchParams (that only sees the query string).
 */
export default function OAuthCallback() {
  const navigate = useNavigate();
  const setTokens = useAuthStore((s) => s.setTokens);
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const errorParam = searchParams.get("error");
    if (errorParam) {
      setError(
        errorParam === "oauth_no_email"
          ? "Your Google account didn't share an email address."
          : errorParam === "account_disabled"
            ? "This account has been disabled."
            : "Google sign-in failed. Please try again."
      );
      return;
    }

    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const accessToken = hash.get("access_token");
    const refreshToken = hash.get("refresh_token");

    if (accessToken && refreshToken) {
      setTokens(accessToken, refreshToken);
      navigate("/", { replace: true });
    } else {
      setError("Something went wrong completing sign-in.");
    }
  }, [navigate, searchParams, setTokens]);

  return (
    <div className="min-h-screen bg-cream flex items-center justify-center px-6">
      <p className="text-ink-muted">
        {error ?? "Finishing sign-in…"}
        {error && (
          <>
            {" "}
            <a href="/login" className="text-gold-600 font-medium">
              Back to sign in
            </a>
          </>
        )}
      </p>
    </div>
  );
}
