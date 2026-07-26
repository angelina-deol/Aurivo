import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Card } from "@/components/ui/Card";
import { useAuthStore } from "@/hooks/useAuthStore";
import { investigationsApi, InvestigationResponse } from "@/services/api";

const PAGE_SIZE = 10;

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

const STATUS_OPTIONS = [
  { value: "", label: "Any status" },
  { value: "complete", label: "Complete" },
  { value: "processing", label: "Processing" },
  { value: "failed", label: "Failed" },
];

const PREDICTION_OPTIONS = [
  { value: "", label: "Any result" },
  { value: "real", label: "Real" },
  { value: "ai_generated", label: "AI Generated" },
];

export default function History() {
  const accessToken = useAuthStore((s) => s.accessToken);

  const [items, setItems] = useState<InvestigationResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [predictionFilter, setPredictionFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;

    // Debounce search-as-you-type; filters/pagination apply immediately.
    const handle = window.setTimeout(
      () => {
        setLoading(true);
        investigationsApi
          .list(accessToken, {
            limit: PAGE_SIZE,
            offset: page * PAGE_SIZE,
            search: search || undefined,
            status: statusFilter || undefined,
            prediction: predictionFilter || undefined,
          })
          .then((res) => {
            setItems(res.items);
            setTotal(res.total);
            setError(null);
          })
          .catch((err) => setError(err instanceof Error ? err.message : "Could not load history"))
          .finally(() => setLoading(false));
      },
      search ? 300 : 0
    );

    return () => window.clearTimeout(handle);
  }, [accessToken, page, search, statusFilter, predictionFilter]);

  // Reset to page 0 whenever a filter changes (not on page changes themselves).
  useEffect(() => {
    setPage(0);
  }, [search, statusFilter, predictionFilter]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="min-h-screen bg-cream px-6 py-12 md:px-16">
      <div className="max-w-3xl mx-auto">
        <h1 className="font-display text-2xl font-semibold text-ink mb-6">
          Investigation history
        </h1>

        <div className="flex flex-col sm:flex-row gap-3 mb-6">
          <input
            type="text"
            placeholder="Search by filename…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 rounded-2xl border border-ink/10 px-4 py-2.5 bg-white focus:border-gold-500"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-2xl border border-ink/10 px-4 py-2.5 bg-white text-ink-muted"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <select
            value={predictionFilter}
            onChange={(e) => setPredictionFilter(e.target.value)}
            className="rounded-2xl border border-ink/10 px-4 py-2.5 bg-white text-ink-muted"
          >
            {PREDICTION_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {error && <p className="text-risk-danger mb-4">{error}</p>}

        {!loading && items.length === 0 && (
          <Card className="text-center text-ink-muted">
            {search || statusFilter || predictionFilter
              ? "No investigations match those filters."
              : "No investigations yet."}
          </Card>
        )}

        <div className="space-y-3">
          {items.map((inv) => (
            <Link key={inv.id} to={`/investigations/${inv.id}`}>
              <Card className="flex items-center justify-between hover:shadow-soft-lg transition-shadow">
                <div className="min-w-0">
                  <p className="font-medium text-ink truncate">{inv.filename}</p>
                  <p className="text-xs text-ink-faint font-mono">{formatDate(inv.created_at)}</p>
                </div>
                <div className="flex items-center gap-4 shrink-0 ml-4">
                  {inv.status === "complete" && inv.prediction && (
                    <span
                      className={`text-xs font-mono px-2 py-1 rounded-full ${
                        inv.prediction === "ai_generated"
                          ? "bg-red-50 text-risk-danger"
                          : "bg-gold-50 text-gold-700"
                      }`}
                    >
                      {inv.prediction === "ai_generated" ? "AI Generated" : "Real"}
                      {inv.confidence !== null ? ` · ${Math.round(inv.confidence * 100)}%` : ""}
                    </span>
                  )}
                  <span className="font-mono text-xs uppercase tracking-widest text-ink-faint">
                    {inv.status.replace("_", " ")}
                  </span>
                </div>
              </Card>
            </Link>
          ))}
        </div>

        {total > PAGE_SIZE && (
          <div className="flex items-center justify-center gap-4 mt-6">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="text-sm text-ink-muted disabled:opacity-30"
            >
              Previous
            </button>
            <span className="font-mono text-xs text-ink-faint">
              Page {page + 1} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="text-sm text-ink-muted disabled:opacity-30"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
