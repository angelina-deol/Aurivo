import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { useAuthStore } from "@/hooks/useAuthStore";
import { investigationsApi, InvestigationStatsResponse } from "@/services/api";

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <p className="font-mono text-xs uppercase tracking-widest text-ink-faint mb-2">{label}</p>
      <p className="font-display text-3xl font-semibold text-ink">{value}</p>
    </Card>
  );
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

const CHART_GOLD = "#E8B330";
const CHART_DANGER = "#C1432E";
const CHART_MUTED = "#A7A18C";

export default function Dashboard() {
  const accessToken = useAuthStore((s) => s.accessToken);
  const [stats, setStats] = useState<InvestigationStatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    investigationsApi
      .stats(accessToken)
      .then(setStats)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load dashboard"));
  }, [accessToken]);

  if (error) {
    return (
      <div className="min-h-screen bg-cream px-6 py-12 md:px-16">
        <p className="text-risk-danger">{error}</p>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="min-h-screen bg-cream px-6 py-12 md:px-16">
        <p className="text-ink-muted">Loading dashboard…</p>
      </div>
    );
  }

  const uploadTrend = stats.daily_uploads.map((p) => ({ date: shortDate(p.date), count: p.count }));
  const fraudTrend = stats.daily_fraud_rate.map((p) => ({ date: shortDate(p.date), rate: p.value }));
  const latencyTrend = stats.daily_avg_latency.map((p) => ({ date: shortDate(p.date), latency: p.value }));
  const histogram = stats.confidence_histogram.map((b) => ({ label: b.label, count: b.count }));
  const distribution = [
    { name: "Real", value: stats.real_count, color: CHART_GOLD },
    { name: "AI Generated", value: stats.fraud_detected_count, color: CHART_DANGER },
  ];

  return (
    <div className="min-h-screen bg-cream px-6 py-12 md:px-16">
      <div className="max-w-4xl mx-auto space-y-6">
        <h1 className="font-display text-2xl font-semibold text-ink">Dashboard</h1>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Today's analyses" value={String(stats.today_analyses_count)} />
          <StatCard label="Fraud detected" value={String(stats.fraud_detected_count)} />
          <StatCard
            label="Avg. confidence"
            value={
              stats.average_confidence !== null ? `${Math.round(stats.average_confidence * 100)}%` : "—"
            }
          />
          <StatCard
            label="Avg. latency"
            value={
              stats.average_processing_time_seconds !== null
                ? `${stats.average_processing_time_seconds.toFixed(1)}s`
                : "—"
            }
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Detection trend</CardTitle>
          </CardHeader>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={fraudTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F5E8C8" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#A7A18C" }} />
                <YAxis tick={{ fontSize: 11, fill: "#A7A18C" }} unit="%" />
                <Tooltip formatter={(value: number) => [`${value}%`, "Fraud rate"]} />
                <Line type="monotone" dataKey="rate" stroke={CHART_DANGER} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <div className="grid md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Daily uploads</CardTitle>
            </CardHeader>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={uploadTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F5E8C8" />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#A7A18C" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#A7A18C" }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill={CHART_GOLD} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Detection distribution</CardTitle>
            </CardHeader>
            <div className="h-48 flex items-center justify-center">
              {stats.real_count + stats.fraud_detected_count === 0 ? (
                <p className="text-ink-faint text-sm">No completed analyses yet</p>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={distribution} dataKey="value" nameKey="name" innerRadius={40} outerRadius={65}>
                      {distribution.map((entry) => (
                        <Cell key={entry.name} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Confidence histogram</CardTitle>
            </CardHeader>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={histogram}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F5E8C8" />
                  <XAxis dataKey="label" tick={{ fontSize: 9, fill: "#A7A18C" }} interval={1} />
                  <YAxis tick={{ fontSize: 11, fill: "#A7A18C" }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill={CHART_MUTED} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Processing latency</CardTitle>
            </CardHeader>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={latencyTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F5E8C8" />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#A7A18C" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#A7A18C" }} unit="s" />
                  <Tooltip formatter={(value: number) => [`${value}s`, "Avg. latency"]} />
                  <Line type="monotone" dataKey="latency" stroke={CHART_GOLD} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
