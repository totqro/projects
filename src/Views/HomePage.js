import { useEffect, useState } from "react";
import { fetchRepos, getStatus } from "../services/github";
import "./HomePage.css";

const STATUS_META = {
  "in-progress": { label: "In Progress", className: "badge--progress" },
  completed: { label: "Completed", className: "badge--completed" },
  archived: { label: "Archived", className: "badge--archived" },
  "on-hold": { label: "On Hold", className: "badge--hold" },
  active: { label: "Active", className: "badge--active" },
};

const LANGUAGE_COLORS = {
  JavaScript: "#f7df1e",
  TypeScript: "#3178c6",
  Python: "#3572a5",
  HTML: "#e34c26",
  CSS: "#563d7c",
  "C++": "#f34b7d",
  Go: "#00add8",
  Rust: "#dea584",
  Java: "#b07219",
  Ruby: "#701516",
};

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.active;
  return <span className={`badge ${meta.className}`}>{meta.label}</span>;
}

function LanguageDot({ language }) {
  if (!language) return null;
  const color = LANGUAGE_COLORS[language] || "#8b949e";
  return (
    <span className="lang">
      <span className="lang__dot" style={{ background: color }} />
      {language}
    </span>
  );
}

function ProjectCard({ repo }) {
  const status = getStatus(repo);

  return (
    <div className="card">
      <div className="card__top">
        <h3 className="card__name">{repo.name}</h3>
        <StatusBadge status={status} />
      </div>

      {repo.description && (
        <p className="card__desc">{repo.description}</p>
      )}

      <div className="card__meta">
        <LanguageDot language={repo.language} />
        {repo.stars > 0 && (
          <span className="card__stars">&#9733; {repo.stars}</span>
        )}
      </div>

      <div className="card__links">
        <a
          href={repo.url}
          target="_blank"
          rel="noopener noreferrer"
          className="card__link card__link--gh"
        >
          GitHub &rarr;
        </a>
        {repo.homepage && (
          <a
            href={repo.homepage}
            target="_blank"
            rel="noopener noreferrer"
            className="card__link card__link--live"
          >
            Live &rarr;
          </a>
        )}
      </div>
    </div>
  );
}

export default function HomePage() {
  const [repos, setRepos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");

  const username = process.env.REACT_APP_GITHUB_USERNAME || "your-username";

  useEffect(() => {
    fetchRepos()
      .then(setRepos)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const statuses = ["all", "in-progress", "active", "completed", "archived", "on-hold"];

  const filtered =
    filter === "all"
      ? repos
      : repos.filter((r) => getStatus(r) === filter);

  return (
    <div className="hub">
      <header className="hub__header">
        <div className="hub__header-inner">
          <div>
            <h1 className="hub__title">Project Hub</h1>
            <p className="hub__sub">
              <a
                href={`https://github.com/${username}`}
                target="_blank"
                rel="noopener noreferrer"
                className="hub__gh-link"
              >
                @{username}
              </a>{" "}
              &middot; {repos.length} projects
            </p>
          </div>
        </div>
      </header>

      <main className="hub__main">
        <div className="hub__filters">
          {statuses.map((s) => (
            <button
              key={s}
              className={`filter-btn ${filter === s ? "filter-btn--active" : ""}`}
              onClick={() => setFilter(s)}
            >
              {s === "all" ? "All" : STATUS_META[s]?.label || s}
            </button>
          ))}
        </div>

        {loading && (
          <div className="hub__state">
            <div className="spinner" />
            <p>Fetching repos…</p>
          </div>
        )}

        {error && (
          <div className="hub__state hub__state--error">
            <p>&#9888; {error}</p>
            {error.includes("REACT_APP_GITHUB_USERNAME") && (
              <p className="hint">
                Add <code>REACT_APP_GITHUB_USERNAME=your-username</code> to your{" "}
                <code>.env</code> file and restart the dev server.
              </p>
            )}
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <div className="hub__state">
            <p>No projects match this filter.</p>
          </div>
        )}

        <div className="grid">
          {filtered.map((repo) => (
            <ProjectCard key={repo.id} repo={repo} />
          ))}
        </div>
      </main>
    </div>
  );
}
