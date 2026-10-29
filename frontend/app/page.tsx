 "use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity, AlertCircle, BarChart3, CheckCircle2, Coffee, Download,
  LayoutDashboard, MessageSquareText, Search, Settings2, RefreshCw,
  Clock3, ThumbsUp, TrendingUp
} from "lucide-react";

type AIReport = {
  generated_at: string; total_reviews: number; sentiment_percentages: Record<string, number>;
  sentiment_counts: Record<string, number>; category_breakdown: { category: string; total: number; negative: number; mixed: number }[];
  executive_summary: string; recommendations: { priority: string; title: string; evidence: string; action: string }[];
};

type Review = {
  id: string | number;
  created_at?: string;
  branch_id?: string;
  review_text: string;
  sentiment: "positive" | "negative" | "mixed" | "neutral";
  category?: string;
  ai_summary?: string;
  complaint_status?: string;
  source?: string;
};

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const demoReviews: Review[] = [
  { id: "demo-1", created_at: new Date().toISOString(), branch_id: "Niloufer — Main", review_text: "The Irani chai was amazing and the service was excellent.", sentiment: "positive", category: "food_quality", ai_summary: "Excellent chai and service.", complaint_status: "not_applicable", source: "portal_demo" },
  { id: "demo-2", created_at: new Date().toISOString(), branch_id: "Niloufer — Main", review_text: "My chai was cold and we waited 25 minutes.", sentiment: "negative", category: "waiting_time", ai_summary: "Cold chai and long waiting time.", complaint_status: "pending", source: "portal_demo" },
  { id: "demo-3", created_at: new Date().toISOString(), branch_id: "Niloufer — Main", review_text: "Great chai, but the tables were dirty.", sentiment: "mixed", category: "cleanliness", ai_summary: "Positive chai feedback with a table cleanliness complaint.", complaint_status: "pending", source: "portal_demo" },
  { id: "demo-4", created_at: new Date().toISOString(), branch_id: "Niloufer — Main", review_text: "Prices are a little high for the portion size.", sentiment: "negative", category: "pricing", ai_summary: "Concern about pricing and portion size.", complaint_status: "in_progress", source: "portal_demo" },
  { id: "demo-5", created_at: new Date().toISOString(), branch_id: "Niloufer — Main", review_text: "Nice ambience, will visit again.", sentiment: "positive", category: "ambience", ai_summary: "Positive ambience feedback.", complaint_status: "not_applicable", source: "portal_demo" }
];

const sentimentLabel: Record<string, string> = {
  positive: "Positive", negative: "Negative", mixed: "Mixed", neutral: "Neutral"
};

function pretty(value?: string) {
  return (value || "other").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function Home() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [connection, setConnection] = useState("Connecting");
  const [search, setSearch] = useState("");
  const [sentimentFilter, setSentimentFilter] = useState("all");
  const [activeNav, setActiveNav] = useState("Overview");
  const [updatingId, setUpdatingId] = useState<string | number | null>(null);
  const [aiReport, setAiReport] = useState<AIReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState("");

  async function loadReviews() {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/reviews`, { cache: "no-store" });
      if (!response.ok) throw new Error("API unavailable");
      const data = await response.json();
      setReviews(Array.isArray(data.reviews) ? data.reviews : []);
      setConnection("Connected");
    } catch {
      setReviews([]);
      setConnection("Backend not connected");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadReviews(); }, []);

  async function generateAIReport() {
    setReportLoading(true);
    setReportError("");
    try {
      const response = await fetch(`${API_URL}/api/ai-report`, { method: "POST", cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not generate the AI report.");
      setAiReport(data as AIReport);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : "Could not generate the AI report. Check the backend logs.");
    } finally {
      setReportLoading(false);
    }
  }

  function downloadAIReport() {
    if (!aiReport) return;
    const lines = [
      "Niloufer Cafe — AI Customer Feedback Report",
      `Generated: ${new Date(aiReport.generated_at).toLocaleString()}`,
      `Total reviews: ${aiReport.total_reviews}`,
      "",
      "Sentiment percentages:",
      ...Object.entries(aiReport.sentiment_percentages).map(([key, value]) => `${pretty(key)}: ${value}% (${aiReport.sentiment_counts[key] || 0})`),
      "",
      "Executive summary:", aiReport.executive_summary,
      "", "Recommendations:",
      ...aiReport.recommendations.flatMap((item, i) => [`${i + 1}. [${item.priority}] ${item.title}`, `Evidence: ${item.evidence}`, `Action: ${item.action}`, ""])
    ].join("\n");
    const blob = new Blob([lines], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "niloufer-ai-report.txt"; a.click();
    URL.revokeObjectURL(url);
  }

  const stats = useMemo(() => ({
    total: reviews.length,
    positive: reviews.filter((r) => r.sentiment === "positive").length,
    negative: reviews.filter((r) => r.sentiment === "negative").length,
    mixed: reviews.filter((r) => r.sentiment === "mixed").length,
    open: reviews.filter((r) => ["pending", "in_progress"].includes(r.complaint_status || "")).length
  }), [reviews]);

  const filtered = reviews.filter((r) => {
    const matchSentiment = sentimentFilter === "all" || r.sentiment === sentimentFilter;
    const matchSearch = `${r.review_text} ${r.category} ${r.ai_summary} ${r.branch_id}`.toLowerCase().includes(search.toLowerCase());
    const matchNav = activeNav !== "Complaints" || ["negative", "mixed"].includes(r.sentiment);
    return matchSentiment && matchSearch && matchNav;
  });

  async function updateStatus(review: Review, status: string) {
    if (String(review.id).startsWith("demo-")) {
      setReviews((prev) => prev.map((r) => r.id === review.id ? { ...r, complaint_status: status } : r));
      return;
    }
    setUpdatingId(review.id);
    try {
      const response = await fetch(`${API_URL}/api/reviews/${encodeURIComponent(String(review.id))}/status`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status })
      });
      if (!response.ok) throw new Error("Status update failed");
      await loadReviews();
    } catch {
      alert("Could not update status. Check the backend connection.");
    } finally {
      setUpdatingId(null);
    }
  }

  function downloadCsv() {
    const headers = ["id", "created_at", "branch_id", "review_text", "sentiment", "category", "ai_summary", "complaint_status", "source"];
    const csvCell = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;
    const csv = [headers.join(","), ...filtered.map((r) => headers.map((h) => csvCell((r as unknown as Record<string, unknown>)[h])).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "niloufer-reviews.csv"; a.click();
    URL.revokeObjectURL(url);
  }

  const maxSentiment = Math.max(stats.positive, stats.negative, stats.mixed, 1);
  const navItems = [
    { name: "Overview", icon: LayoutDashboard },
    { name: "All Reviews", icon: MessageSquareText },
    { name: "Complaints", icon: AlertCircle },
    { name: "AI Report", icon: BarChart3 }
  ];

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-icon"><Coffee size={23} /></div><div><strong>niloufer</strong><span>EXPERIENCE INTELLIGENCE</span></div></div>
        <div className="workspace-label">WORKSPACE</div>
        <button className="branch-select"><span className="branch-dot" /> Niloufer Café <span className="chevron">⌄</span></button>
        <nav>
          {navItems.map(({ name, icon: Icon }) => <button key={name} onClick={() => setActiveNav(name)} className={`nav-item ${activeNav === name ? "active" : ""}`}><Icon size={18} />{name}{name === "Complaints" && stats.open > 0 && <span className="nav-count">{stats.open}</span>}</button>)}
        </nav>
        <div className="sidebar-bottom"><button className="nav-item" onClick={() => setActiveNav("Settings")}><Settings2 size={18} /> Settings</button><div className="profile"><div className="avatar">N</div><div><strong>Niloufer Admin</strong><span>Workspace owner</span></div><span className="dots">···</span></div></div>
      </aside>

      <section className="content">
        <header className="topbar"><div className="crumb">Workspace <span>/</span> <b>{activeNav}</b></div><div className="top-actions"><span className={`connection ${connection === "Connected" ? "good" : ""}`}><i />{connection}</span><button className="icon-button" aria-label="Refresh" onClick={() => void loadReviews()}><RefreshCw size={16} /></button><div className="avatar small">N</div></div></header>

        <div className="page">
          <div className="page-heading"><div><div className="eyebrow">CUSTOMER EXPERIENCE · HYDERABAD</div><h1>{activeNav === "Complaints" ? "Complaint centre" : activeNav === "AI Report" ? "AI customer report" : activeNav === "Settings" ? "Workspace settings" : activeNav === "All Reviews" ? "Customer reviews" : "Good morning, Niloufer"}<span className="heading-dot">.</span></h1><p>Understand every customer voice. Make every visit better.</p></div><button className="primary-button" onClick={downloadCsv}><Download size={16} /> Export report</button></div>

          {activeNav === "AI Report" ? (
            <>
              <section className="panel" style={{ padding: 24, marginBottom: 20 }}>
                <div className="reviews-heading" style={{ alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                  <div><h2>AI Customer Feedback Report</h2><p>Analyze real reviews from your connected database and find actionable improvements.</p></div>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <button className="primary-button" onClick={() => void generateAIReport()} disabled={reportLoading || loading || reviews.length === 0}>
                      <BarChart3 size={16} /> {reportLoading ? "Analyzing feedback…" : aiReport ? "Refresh AI report" : "Generate AI report"}
                    </button>
                    {aiReport && <button className="filter-button" onClick={downloadAIReport}><Download size={15} /> Download report</button>}
                  </div>
                </div>
                {reportError && <div className="insight-callout" style={{ marginTop: 16 }}><AlertCircle size={18} /><p>{reportError}</p></div>}
                {!aiReport && !reportError && <p style={{ marginTop: 18, color: "var(--muted, #777)" }}>{loading ? "Loading reviews…" : reviews.length === 0 ? "No reviews are available yet. Receive customer feedback first, then generate a report." : `${reviews.length} real review(s) are available. Click Generate AI report to calculate sentiment percentages and create recommendations.`}</p>}
              </section>
              {aiReport && <>
                <div className="stats-grid">
                  {[
                    { label: "Total reviews", value: aiReport.total_reviews, icon: <MessageSquareText size={18} />, tone: "cream" },
                    { label: "Positive feedback", value: `${aiReport.sentiment_percentages.positive ?? 0}%`, icon: <ThumbsUp size={18} />, tone: "green" },
                    { label: "Negative feedback", value: `${aiReport.sentiment_percentages.negative ?? 0}%`, icon: <AlertCircle size={18} />, tone: "red" },
                    { label: "Mixed feedback", value: `${aiReport.sentiment_percentages.mixed ?? 0}%`, icon: <Activity size={18} />, tone: "gold" }
                  ].map((card) => <div className="stat-card" key={card.label}><div className="stat-top"><span>{card.label}</span><span className={`stat-icon ${card.tone}`}>{card.icon}</span></div><div className="stat-value">{card.value}</div><div className="stat-foot">Calculated from stored reviews</div></div>)}
                </div>
                <div className="middle-grid" style={{ marginTop: 20 }}>
                  <section className="panel sentiment-panel"><div className="panel-heading"><div><h2>Sentiment distribution</h2><p>Percentage of all recorded reviews</p></div></div>
                    {Object.entries(aiReport.sentiment_percentages).map(([sentiment, percentage]) => <div className="bar-row" key={sentiment}><div className="bar-label"><span>{pretty(sentiment)}</span><strong>{percentage}% · {aiReport.sentiment_counts[sentiment] || 0}</strong></div><div className="bar-track"><div className={`bar-fill ${sentiment}`} style={{ width: `${percentage}%` }} /></div></div>)}
                  </section>
                  <section className="panel insight-panel"><div className="panel-heading"><div><h2>Executive summary</h2><p>AI-generated from customer feedback</p></div><span className="spark">✳</span></div><p style={{ lineHeight: 1.7, whiteSpace: "pre-wrap" }}>{aiReport.executive_summary}</p><p className="source" style={{ marginTop: 14 }}>Generated {new Date(aiReport.generated_at).toLocaleString()}</p></section>
                </div>
                <section className="panel" style={{ padding: 24, marginTop: 20 }}><div className="panel-heading"><div><h2>What can we improve?</h2><p>Prioritized recommendations with evidence from customer reviews</p></div></div>
                  {aiReport.recommendations.length === 0 ? <p>No recurring improvement themes were identified in the available reviews.</p> : aiReport.recommendations.map((item, index) => <div key={`${item.title}-${index}`} style={{ padding: "18px 0", borderBottom: index === aiReport.recommendations.length - 1 ? 0 : "1px solid var(--border, #e7e3dc)" }}><div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}><span className={`pill ${item.priority.toLowerCase() === "high" ? "negative" : item.priority.toLowerCase() === "medium" ? "mixed" : "positive"}`}>{pretty(item.priority)} priority</span><strong>{item.title}</strong></div><p style={{ margin: "10px 0 6px", lineHeight: 1.6 }}><b>Evidence:</b> {item.evidence}</p><p style={{ margin: 0, lineHeight: 1.6 }}><b>Recommended action:</b> {item.action}</p></div>)}
                </section>
                <section className="panel" style={{ padding: 24, marginTop: 20 }}><div className="panel-heading"><div><h2>Feedback by category</h2><p>Categories with negative or mixed feedback</p></div></div>
                  {aiReport.category_breakdown.length === 0 ? <p>No category data available.</p> : <div className="table-wrap"><table><thead><tr><th>CATEGORY</th><th>TOTAL REVIEWS</th><th>NEGATIVE</th><th>MIXED</th></tr></thead><tbody>{aiReport.category_breakdown.map((row) => <tr key={row.category}><td>{pretty(row.category)}</td><td>{row.total}</td><td>{row.negative}</td><td>{row.mixed}</td></tr>)}</tbody></table></div>}
                </section>
              </>}
            </>
          ) : activeNav === "Settings" ? <section className="panel" style={{ padding: 24 }}><h2>Workspace settings</h2><p>Report data is read from your connected review database. Keep your API keys on the backend, never in the frontend.</p></section> : <>
          <div className="stats-grid">
            <div className="stat-card"><div className="stat-top"><span>Total reviews</span><span className="stat-icon cream"><MessageSquareText size={18} /></span></div><div className="stat-value">{stats.total}</div><div className="stat-foot"><Activity size={14} /> Feedback captured</div></div>
            <div className="stat-card"><div className="stat-top"><span>Positive reviews</span><span className="stat-icon green"><ThumbsUp size={18} /></span></div><div className="stat-value">{stats.positive}</div><div className="stat-foot green-text"><TrendingUp size={14} /> Happy customers</div></div>
            <div className="stat-card"><div className="stat-top"><span>Negative reviews</span><span className="stat-icon red"><AlertCircle size={18} /></span></div><div className="stat-value">{stats.negative}</div><div className="stat-foot red-text">Needs attention</div></div>
            <div className="stat-card"><div className="stat-top"><span>Open complaints</span><span className="stat-icon gold"><Clock3 size={18} /></span></div><div className="stat-value">{stats.open}</div><div className="stat-foot">Pending resolution</div></div>
          </div>

          <div className="middle-grid">
            <section className="panel sentiment-panel"><div className="panel-heading"><div><h2>Sentiment overview</h2><p>How customers feel about their visit</p></div><span className="period-tag">ALL TIME</span></div>
              {["positive", "negative", "mixed"].map((s) => {
                const count = stats[s as "positive" | "negative" | "mixed"];
                return <div className="bar-row" key={s}><div className="bar-label"><span>{sentimentLabel[s]}</span><strong>{count}</strong></div><div className="bar-track"><div className={`bar-fill ${s}`} style={{ width: `${count / maxSentiment * 100}%` }} /></div></div>;
              })}
              <div className="sentiment-note"><CheckCircle2 size={17} /><span>Feedback is categorized automatically. Review AI labels before making business decisions.</span></div>
            </section>
            <section className="panel insight-panel"><div className="panel-heading"><div><h2>Focus for today</h2><p>Signals from customer feedback</p></div><span className="spark">✳</span></div>
              {stats.open > 0 ? <div className="insight-callout"><span className="callout-icon"><AlertCircle size={17} /></span><div><strong>{stats.open} complaint{stats.open === 1 ? "" : "s"} need attention</strong><p>Review negative and mixed feedback and assign follow-up to the right team.</p></div></div> : <div className="insight-callout"><span className="callout-icon"><CheckCircle2 size={17} /></span><div><strong>No open complaints</strong><p>You're all caught up on the feedback recorded so far.</p></div></div>}
              <div className="insight-bottom"><span>Mixed feedback</span><strong>{stats.mixed} <small>reviews</small></strong></div>
            </section>
          </div>

          <section className="panel reviews-panel"><div className="reviews-heading"><div><h2>{activeNav === "Complaints" ? "Complaints to review" : "Latest customer feedback"}</h2><p>Real-time review inbox from connected channels</p></div><button className="text-button" onClick={() => setActiveNav("All Reviews")}>View all reviews <span>→</span></button></div>
            <div className="table-tools"><div className="search-box"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search reviews, categories..." /></div><select value={sentimentFilter} onChange={(e) => setSentimentFilter(e.target.value)} aria-label="Filter sentiment"><option value="all">All sentiment</option><option value="positive">Positive</option><option value="negative">Negative</option><option value="mixed">Mixed</option><option value="neutral">Neutral</option></select><button className="filter-button" onClick={() => { setSearch(""); setSentimentFilter("all"); }}><Settings2 size={15} /> Reset</button></div>
            {loading ? <div className="empty-state">Loading reviews…</div> : filtered.length === 0 ? <div className="empty-state">{connection === "Connected" ? "No reviews match these filters." : "Backend not connected. Start the FastAPI backend and configure NEXT_PUBLIC_API_URL. Demo reviews are not shown as live data."}</div> : <div className="table-wrap"><table><thead><tr><th>CUSTOMER FEEDBACK</th><th>SENTIMENT</th><th>CATEGORY</th><th>STATUS</th><th>RECEIVED</th></tr></thead><tbody>{filtered.map((r) => <tr key={r.id}><td><div className="review-text">{r.review_text}</div><div className="review-summary">{r.ai_summary || "—"}</div></td><td><span className={`pill ${r.sentiment}`}>{sentimentLabel[r.sentiment] || pretty(r.sentiment)}</span></td><td><span className="category">{pretty(r.category)}</span></td><td>{["negative","mixed"].includes(r.sentiment) ? <select className={`status-select ${r.complaint_status}`} value={r.complaint_status || "pending"} disabled={updatingId === r.id} onChange={(e) => void updateStatus(r, e.target.value)} aria-label={`Status for review ${r.id}`}><option value="pending">Pending</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option></select> : <span className="muted-status">Recorded</span>}</td><td><span className="date">{r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}</span><span className="source">{pretty(r.source)}</span></td></tr>)}</tbody></table></div>}
            <div className="table-footer"><span>Showing {filtered.length} of {reviews.length} reviews</span><span><i className="live-dot" /> Live data when backend is connected</span></div>
          </section>
          </>}
          <footer className="footer"><span>© {new Date().getFullYear()} Niloufer Experience Intelligence</span><span>Made for better customer experiences <span className="heart">♥</span></span></footer>
        </div>
      </section>
    </main>
  );
}
