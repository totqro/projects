const GITHUB_USERNAME = process.env.REACT_APP_GITHUB_USERNAME;
const GITHUB_TOKEN = process.env.REACT_APP_GITHUB_TOKEN; // optional, increases rate limit
const headers = GITHUB_TOKEN
  ? { Authorization: `token ${GITHUB_TOKEN}` }
  : {};

export async function fetchRepos() {
  if (!GITHUB_USERNAME) {
    throw new Error("REACT_APP_GITHUB_USERNAME is not set in your .env file");
  }

  const url = `https://api.github.com/users/${GITHUB_USERNAME}/repos?sort=updated&per_page=100`;
  const res = await fetch(url, { headers });

  if (!res.ok) {
    throw new Error(`GitHub API error: ${res.status} ${res.statusText}`);
  }

  const repos = await res.json();

  // Filter out forked repos and map to our shape
  return repos
    .filter((r) => !r.fork)
    .map((r) => ({
      id: r.id,
      name: r.name,
      description: r.description || "",
      url: r.html_url,
      homepage: r.homepage || null,
      language: r.language || null,
      topics: r.topics || [],
      stars: r.stargazers_count,
      updatedAt: r.updated_at,
      archived: r.archived,
    }));
}

/**
 * Derive a status from repo topics.
 * Tag your GitHub repo with one of: in-progress, completed, archived
 */
export function getStatus(repo) {
  if (repo.archived) return "archived";
  if (repo.topics.includes("completed")) return "completed";
  if (repo.topics.includes("in-progress")) return "in-progress";
  if (repo.topics.includes("on-hold")) return "on-hold";
  return "active";
}
