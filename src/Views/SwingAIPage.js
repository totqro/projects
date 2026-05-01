import { Link } from "react-router-dom";
import "./SwingAIPage.css";

const METRICS = [
  { name: "Tempo Ratio", desc: "Backswing ÷ downswing time", unit: ":1" },
  { name: "Spine Tilt", desc: "Forward lean angle at address", unit: "°" },
  { name: "Knee Flex", desc: "Knee bend at address", unit: "°" },
  { name: "Lead Arm", desc: "Elbow angle at top of backswing", unit: "°" },
  { name: "Hand Height", desc: "Wrist height at top (normalised)", unit: "" },
  { name: "Head Drift", desc: "Max lateral head movement", unit: "%" },
  { name: "Shoulder Turn", desc: "Shoulder-line tilt from address to top", unit: "°" },
  { name: "Hip Turn", desc: "Hip-line tilt from address to top", unit: "°" },
  { name: "X-Factor", desc: "Shoulder turn − Hip turn", unit: "°" },
];

const TECH = [
  { label: "Swift / SwiftUI", sub: "iOS 17+" },
  { label: "Apple Vision", sub: "Body pose estimation" },
  { label: "AVFoundation", sub: "120fps rear camera" },
  { label: "Anthropic API", sub: "claude-haiku-4-5 coaching tips" },
];

export default function SwingAIPage() {
  return (
    <div className="sai">
      <nav className="sai__nav">
        <Link to="/" className="sai__back">
          &larr; All Projects
        </Link>
      </nav>

      {/* ── Hero ──────────────────────────────────────────────── */}
      <header className="sai__hero">
        <div className="sai__hero-inner">
          <div className="sai__badge-row">
            <span className="sai__tag">iOS App</span>
            <span className="sai__tag sai__tag--green">In Progress</span>
          </div>
          <h1 className="sai__title">SwingAI</h1>
          <p className="sai__tagline">
            {/* CONTENT: one-line tagline goes here */}
            AI-powered golf swing analysis — record, measure, improve.
          </p>
          <div className="sai__links">
            {/* CONTENT: add GitHub / demo links */}
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="sai__link sai__link--gh"
            >
              GitHub &rarr;
            </a>
          </div>
        </div>
      </header>

      <main className="sai__main">

        {/* ── Overview ──────────────────────────────────────────── */}
        <section className="sai__section">
          <h2 className="sai__section-title">Overview</h2>
          <p className="sai__body">
            {/* CONTENT: project overview paragraph */}
            Placeholder — overview coming soon.
          </p>
        </section>

        {/* ── Demo / Screenshots ────────────────────────────────── */}
        <section className="sai__section">
          <h2 className="sai__section-title">Demo</h2>
          <div className="sai__media-grid">
            {/* CONTENT: replace with actual screenshots / video */}
            <div className="sai__media-placeholder">Screenshot 1</div>
            <div className="sai__media-placeholder">Screenshot 2</div>
            <div className="sai__media-placeholder">Screenshot 3</div>
          </div>
        </section>

        {/* ── Tech Stack ────────────────────────────────────────── */}
        <section className="sai__section">
          <h2 className="sai__section-title">Tech Stack</h2>
          <div className="sai__tech-grid">
            {TECH.map((t) => (
              <div key={t.label} className="sai__tech-card">
                <span className="sai__tech-label">{t.label}</span>
                <span className="sai__tech-sub">{t.sub}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── How It Works ──────────────────────────────────────── */}
        <section className="sai__section">
          <h2 className="sai__section-title">How It Works</h2>
          <ol className="sai__steps">
            <li>Record up to 3 swings at 120fps through the rear camera</li>
            <li>Apple Vision extracts 15 body-pose keypoints per frame</li>
            <li>Phase detection finds address, top of backswing, and impact</li>
            <li>9 swing metrics are computed and compared against a Rory McIlroy reference</li>
            <li>The Anthropic API generates plain-English coaching tips ranked by severity</li>
          </ol>
        </section>

        {/* ── Metrics ───────────────────────────────────────────── */}
        <section className="sai__section">
          <h2 className="sai__section-title">Metrics Tracked</h2>
          <div className="sai__metrics-table">
            <div className="sai__metrics-row sai__metrics-row--header">
              <span>Metric</span>
              <span>What it measures</span>
              <span>Unit</span>
            </div>
            {METRICS.map((m) => (
              <div key={m.name} className="sai__metrics-row">
                <span className="sai__metric-name">{m.name}</span>
                <span>{m.desc}</span>
                <span className="sai__metric-unit">{m.unit || "—"}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── Extra Content ─────────────────────────────────────── */}
        <section className="sai__section">
          <h2 className="sai__section-title">More</h2>
          <p className="sai__body sai__body--muted">
            {/* CONTENT: additional sections, challenges, learnings, etc. */}
            Additional content coming soon.
          </p>
        </section>

      </main>
    </div>
  );
}
