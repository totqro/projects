let allGames = [], allRecommendations = [];

const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);
const pct = (v, d=1) => (v*100).toFixed(d) + '%';

// Grades by edge, same thresholds as bet_tracker.get_grade (the old
// confidence-based grades read a model-weight number as if it were a
// probability). "Strong" = B+ or better.
function getGrade(edge) { return edge>=.07?'A':edge>=.04?'B+':edge>=.03?'B':'C+'; }
const STRONG_EDGE = 0.04;
const startMs = g => { const t = Date.parse(g.start_time || ''); return isNaN(t) ? Infinity : t; };
const startLabel = g => { const t = Date.parse(g.start_time || ''); return isNaN(t) ? '' :
    new Date(t).toLocaleTimeString('en-US', {hour:'numeric', minute:'2-digit', timeZone:'America/New_York'}) + ' ET'; };
function getGradeClass(g) { return {A:'grade-a','B+':'grade-b-plus',B:'grade-b','C+':'grade-c-plus'}[g]||'grade-c-plus'; }

const TABS = ['today', 'performance', 'bracket'];

function showTab(t) {
    TABS.forEach(name => { const el = $(`${name}-tab`); if (el) el.style.display = 'none'; });
    $$('.tab-button').forEach(b => b.classList.remove('active'));

    const idx = Math.max(0, TABS.indexOf(t));
    const el = $(`${TABS[idx]}-tab`);
    if (el) el.style.display = 'block';
    const btn = $$('.tab-button')[idx];
    if (btn) btn.classList.add('active');

    if (TABS[idx] === 'performance') loadPerformanceData();
    if (TABS[idx] === 'bracket') loadBracketData();
}

async function loadAnalysis() {
    try {
        const r = await fetch(`latest_analysis.json?v=${Date.now()}`);
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        displayAnalysis(await r.json());
        $('loading').style.display = 'none';
        showTab('today');
    } catch(e) {
        console.error(e);
        $('loading').style.display = 'none';
        const el = $('error'); el.style.display = 'block';
        el.innerHTML = `<p>⚠️ Could not load prediction data. Make sure latest_analysis.json is available.</p>`;
    }
}

// Performance History: performance.json holds every logged prediction
// scored against its final score (rebuilt each run), plus the old Mar-Jun
// 2026 backtest as its own season. Stats are computed for the selected season.
let perfData = null;

async function loadPerformanceData() {
    try {
        const r = await fetch(`performance.json?v=${Date.now()}`);
        if (!r.ok) { displayNoPerformanceData(); return; }
        perfData = await r.json();
        const sel = $('perf-season');
        const seasons = perfData.seasons || [];
        // Default to the current season even before its first game is scored.
        const now = new Date();
        const startYr = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
        const current = `${startYr}-${String(startYr + 1).slice(2)}`;
        if (!seasons.some(s => s.key === current)) seasons.unshift({key: current, label: current});
        const prev = sel.value;
        sel.innerHTML = seasons.map(s => `<option value="${s.key}">${s.label}</option>`).join('')
            + `<option value="all">All seasons</option>`;
        sel.value = prev && [...sel.options].some(o => o.value === prev) ? prev : current;
        applyPerfSeason();
    } catch(e) { console.error(e); displayNoPerformanceData(); }
}

function applyPerfSeason() {
    if (!perfData) return;
    const season = $('perf-season').value;
    const results = (perfData.results || []).filter(r => season === 'all' || r.season === season);
    if (!results.length) { displayNoPerformanceData('No completed games scored for this season yet.'); return; }
    const n = results.length;
    const withTotal = results.filter(r => r.total_error != null);
    displayPerformance({
        results,
        winner_accuracy: results.filter(r => r.winner_correct).length / n,
        within_1_goal: withTotal.length ? withTotal.filter(r => r.total_error <= 1).length / withTotal.length : null,
        avg_total_error: withTotal.length ? withTotal.reduce((a, r) => a + r.total_error, 0) / withTotal.length : null,
    });
}

function displayAnalysis(data) {
    const ts = new Date(data.timestamp);
    $('timestamp').textContent = ts.toLocaleString('en-US', {month:'short', day:'numeric', hour:'numeric', minute:'2-digit', timeZone:'America/New_York'}) + ' EST';
    $('games-analyzed').textContent = data.games_analyzed.length;

    allGames = data.games_analyzed;
    allRecommendations = data.recommendations;

    const strong = allRecommendations.filter(r => (r.edge||0) >= STRONG_EDGE);
    $('bets-found').textContent = strong.length;

    if (allRecommendations.length) {
        const avgEdge = allRecommendations.reduce((s, b) => s + (b.edge||0), 0) / allRecommendations.length;
        $('expected-roi').textContent = pct(avgEdge, 1);
    } else {
        $('expected-roi').textContent = 'N/A';
    }

    applySort();
}

function applySort() {
    const sortBy = $('sort-games')?.value || 'time';
    const strongOnly = $('strong-only')?.checked || false;

    const recsByGame = {};
    allRecommendations.forEach(r => {
        if (!recsByGame[r.game]) recsByGame[r.game] = [];
        recsByGame[r.game].push(r);
    });

    let games = [...allGames];

    if (strongOnly) {
        const strongGames = new Set(
            allRecommendations.filter(r => (r.edge||0) >= STRONG_EDGE).map(r => r.game)
        );
        games = games.filter(g => strongGames.has(g.game));
    }

    if (sortBy === 'time') {
        // Earliest puck drop first; games without a start time go last.
        games.sort((a, b) => startMs(a) - startMs(b));
    } else if (sortBy === 'edge') {
        const bestEdge = g => Math.max(0, ...(recsByGame[g.game]||[]).map(r => r.edge||0));
        games.sort((a, b) => bestEdge(b) - bestEdge(a));
    } else {
        games.sort((a, b) => {
            const pa = a.blended_probs || a.model_probs;
            const pb = b.blended_probs || b.model_probs;
            return Math.abs((pb?.home_win_prob||0.5) - 0.5) - Math.abs((pa?.home_win_prob||0.5) - 0.5);
        });
    }

    displayGamePredictions(games, recsByGame);
}

function displayGamePredictions(games, recsByGame) {
    const container = $('games-list');
    if (!games.length) {
        container.innerHTML = `<div class="no-data"><div class="no-data-icon">🏒</div><p>No games found.</p></div>`;
        return;
    }
    container.innerHTML = games.map((g, i) => renderGameCard(g, i, recsByGame[g.game] || [])).join('');
}

function renderGameCard(g, i, gameRecs) {
    const mp = g.model_probs;
    const bp = g.blended_probs || mp;
    const ci = g.context_indicators || {};
    const homeProb = bp.home_win_prob;
    const awayProb = bp.away_win_prob;
    const expectedTotal = mp.expected_total;
    const totalLine = mp.total_line;
    const totalRec = gameRecs.find(r => r.bet_type === 'Total');
    const topEdge = gameRecs.length ? Math.max(...gameRecs.map(r => r.edge||0)) : 0;
    const isStrong = topEdge >= STRONG_EDGE;
    const grade = isStrong ? getGrade(topEdge) : null;
    const timeLabel = startLabel(g);
    const gradeClass = grade ? getGradeClass(grade) : '';

    let ouHtml = '';
    if (totalRec && totalLine) {
        const isOver = (totalRec.pick||'').toLowerCase().startsWith('over');
        ouHtml = ` · <span class="gc-ou ${isOver?'over':'under'}">${isOver?'↑ Over':'↓ Under'}</span>`;
    }

    const homePct = (homeProb*100).toFixed(0);
    const awayPct = (awayProb*100).toFixed(0);
    const homeWins = homeProb > awayProb;
    const contextHtml = renderContextIndicators(ci);

    return `<div class="gc cy-panel${isStrong?' gc-strong':''}" id="gc-${i}">
        <div class="gc-header" onclick="toggleGC(${i})">
            <div class="gc-matchup">
                <span class="${!homeWins?'gc-pick-team':''}">${g.away}</span>
                <span class="gc-sep">@</span>
                <span class="${homeWins?'gc-pick-team':''}">${g.home}</span>
                ${timeLabel ? `<span class="gc-sep">· ${timeLabel}</span>` : ''}
            </div>
            ${grade ? `<span class="grade ${gradeClass} gc-grade">${grade}</span>` : ''}
        </div>
        <div class="gc-probs" onclick="toggleGC(${i})">
            <div class="gc-team-row${!homeWins?' gc-winner':''}">
                <span class="gc-tname">${g.away}</span>
                <div class="gc-bar-wrap"><div class="gc-bar" style="width:${awayPct}%"></div></div>
                <span class="gc-tpct">${awayPct}%</span>
            </div>
            <div class="gc-team-row${homeWins?' gc-winner':''}">
                <span class="gc-tname">${g.home}</span>
                <div class="gc-bar-wrap"><div class="gc-bar" style="width:${homePct}%"></div></div>
                <span class="gc-tpct">${homePct}%</span>
            </div>
        </div>
        <div class="gc-footer" onclick="toggleGC(${i})">
            <div class="gc-total">
                <span class="gc-total-num">${expectedTotal ? expectedTotal.toFixed(1) : '—'}</span>
                <span class="gc-total-unit">exp. goals</span>
                ${totalLine ? `<span class="gc-line">Line ${totalLine}${ouHtml}</span>` : ''}
            </div>
        </div>
        ${contextHtml ? `<div class="gc-context" onclick="toggleGC(${i})">${contextHtml}</div>` : ''}
        <div class="gc-expanded" id="gced-${i}" style="display:none">
            ${renderGameDetails(g)}
        </div>
    </div>`;
}

function toggleGC(i) {
    const el = $(`gced-${i}`);
    const card = $(`gc-${i}`);
    const isOpen = el.style.display !== 'none';
    el.style.display = isOpen ? 'none' : 'block';
    card.classList.toggle('gc-open', !isOpen);
}

function renderContextIndicators(ci) {
    if (!ci || !Object.keys(ci).length) return '';
    const b = [];
    (ci.fatigue||[]).forEach(i => { b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${i.type==='B2B'?'😴':'💪'}</span>${i.team} ${i.type==='B2B'?'B2B':'Rested'}</span>`); });
    (ci.goalie||[]).forEach(i => { const m={hot:['positive','🔥','Hot'],cold:['negative','🧊','Cold'],advantage:['positive','🥅','Goalie']}[i.type]; if(m) b.push(`<span class="context-badge ${m[0]}"><span class="context-icon">${m[1]}</span>${i.team} ${m[2]}</span>`); });
    (ci.injuries||[]).forEach(i => { b.push(`<span class="context-badge negative"><span class="context-icon">🏥</span>${i.team} Injuries</span>`); });
    (ci.splits||[]).forEach(i => { const t={strong_home:'Strong Home',weak_home:'Weak Home',strong_road:'Strong Road',weak_road:'Weak Road'}[i.type]; if(t) b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${i.severity==='positive'?'🏠':'🛣️'}</span>${i.team} ${t}</span>`); });
    return b.length ? `<div class="context-indicators">${b.join('')}</div>` : '';
}

function renderGameDetails(g) {
    let h = '';
    const gm = g.goalie_matchup;
    if (gm?.home && gm?.away) {
        const gc = t => `<div class="goalie-card">
            <div class="goalie-name">${t === gm.home ? g.home : g.away}: ${t.name}</div>
            <div class="goalie-stats">
                <div class="goalie-stat-row"><span class="goalie-stat-label">SV% (L10)</span><span class="goalie-stat-value">.${(t.recent_save_pct*1000).toFixed(0)}</span></div>
                <div class="goalie-stat-row"><span class="goalie-stat-label">GAA (L10)</span><span class="goalie-stat-value">${t.recent_gaa.toFixed(2)}</span></div>
                <div class="goalie-stat-row"><span class="goalie-stat-label">Quality Starts</span><span class="goalie-stat-value">${t.recent_quality_starts}/10</span></div>
            </div>
            <div class="quality-score">${t.quality_score.toFixed(0)}</div>
        </div>`;
        h += `<div class="details-section"><h3>Goalie Matchup</h3><div class="goalie-comparison">${gc(gm.home)}${gc(gm.away)}</div></div>`;
    }
    const sp = g.team_splits;
    if (sp?.home && sp?.away) {
        const sc = (lbl, d) => `<div class="split-card">
            <div class="split-title">${lbl}</div>
            <div class="split-stats">
                <div class="split-stat-row"><span class="split-stat-label">Win %</span><span class="split-stat-value">${pct(d.win_pct)}</span></div>
                <div class="split-stat-row"><span class="split-stat-label">GF/G</span><span class="split-stat-value">${d.gf_pg.toFixed(2)}</span></div>
                <div class="split-stat-row"><span class="split-stat-label">GA/G</span><span class="split-stat-value">${d.ga_pg.toFixed(2)}</span></div>
            </div>
        </div>`;
        h += `<div class="details-section"><h3>Home/Road Splits (L10)</h3><div class="splits-comparison">${sc(g.home + ' at Home', sp.home)}${sc(g.away + ' on Road', sp.away)}</div></div>`;
    }
    const as = g.advanced_stats;
    if (as?.home && as?.away) {
        const s = (t, d) => [['xGF%', d.xGF_pct], ['Corsi%', d.corsi_pct], ['PDO', d.pdo]].map(([l, v]) =>
            `<div class="advanced-stat-card"><div class="advanced-stat-label">${t} ${l}</div><div class="advanced-stat-value">${v.toFixed(1)}${l!=='PDO'?'%':''}</div></div>`
        ).join('');
        h += `<div class="details-section"><h3>Advanced Stats</h3><div class="advanced-stats-grid">${s(g.home, as.home)}${s(g.away, as.away)}</div></div>`;
    }
    if (g.injuries && (g.injuries.home.impact_score > 0 || g.injuries.away.impact_score > 0)) {
        h += `<div class="details-section"><h3>Injury Impact</h3><div class="injury-list">
            ${[['home', g.home], ['away', g.away]].filter(([k]) => g.injuries[k].impact_score > 0).map(([k, t]) =>
                `<div class="injury-item"><span class="injury-team">${t}</span><span class="injury-impact">-${g.injuries[k].impact_score.toFixed(1)} impact</span></div>`
            ).join('')}
        </div></div>`;
    }
    return h;
}

function displayPerformance(data) {
    if (!data?.results?.length) { displayNoPerformanceData(); return; }
    const results = data.results;
    const n = results.length;

    $('perf-total-bets').textContent = n;
    $('perf-win-rate').textContent = data.winner_accuracy != null ? pct(data.winner_accuracy) : '-';
    $('perf-total-within1').textContent = data.within_1_goal != null ? pct(data.within_1_goal) : '-';
    $('perf-total-exact').textContent = data.avg_total_error != null ? data.avg_total_error.toFixed(2) : '-';

    const diffs = results.filter(r => r.predicted_total != null).map(r => Math.abs(Math.round(r.predicted_total) - r.actual_total));
    const greenCount = diffs.filter(d => d === 0).length;
    const yellowCount = diffs.filter(d => d === 1).length;
    const redCount = diffs.filter(d => d >= 2).length;

    $('total-green').textContent = greenCount;
    $('total-yellow').textContent = yellowCount;
    $('total-red').textContent = redCount;
    const nt = Math.max(diffs.length, 1);
    $('total-green-pct').textContent = pct(greenCount / nt);
    $('total-yellow-pct').textContent = pct(yellowCount / nt);
    $('total-red-pct').textContent = pct(redCount / nt);

    renderVegas(results);

    $('recent-results-list').innerHTML = results.slice(0, 60).map(r => {
        const diff = Math.abs(Math.round(r.predicted_total) - r.actual_total);
        const dot = diff === 0 ? '🟢' : diff === 1 ? '🟡' : '🔴';
        const cls = diff === 0 ? 'total-green' : diff === 1 ? 'total-yellow' : 'total-red';
        const winIcon = r.winner_correct ? '✅' : '❌';
        const predicted = Math.round(r.predicted_total);
        const parts = r.actual_score?.split('-') || [];
        const score = parts.length === 2 ? `${parts[0]}–${parts[1]}` : '';
        const d = new Date(r.date + 'T12:00:00');
        const dateStr = d.toLocaleDateString('en-US', {month:'short', day:'numeric'});
        return `<div class="pred-result-row">
            <span class="pred-result-date">${dateStr}</span>
            <span class="pred-result-matchup">${r.game}${r.market_pick ? `<span class="pred-result-date"> · Vegas ${r.market_correct ? '✅' : '❌'} ${r.market_pick} ${pct(r.market_pick_prob, 0)}</span>` : ''}</span>
            <span class="pred-result-winner">${winIcon} ${r.predicted_winner}${score ? `<span class="score"> ${score}</span>` : ''}</span>
            <span class="pred-result-total ${cls}">${dot} ${predicted}<span class="actual"> · ${r.actual_total}</span></span>
        </div>`;
    }).join('');
}

// ---------------------------------------------------------------------------
// Stanley Cup bracket — projected forward from round 1, scored against reality
// ---------------------------------------------------------------------------
let bracketLoaded = false;

async function loadBracketData() {
    if (bracketLoaded) return;
    try {
        const r = await fetch(`playoff_bracket.json?v=${Date.now()}`);
        if (!r.ok) { displayNoBracket(); return; }
        displayBracket(await r.json());
        bracketLoaded = true;
    } catch(e) { console.error(e); displayNoBracket(); }
}

function displayNoBracket() {
    $('bracket-board').innerHTML = `<div class="no-data"><div class="no-data-icon">🏆</div><p>No bracket yet. Run playoff_bracket.py to generate.</p></div>`;
    $('bracket-totals').innerHTML = '';
    ['bracket-season','bracket-correct','bracket-rate','bracket-asof'].forEach(id => $(id).textContent = '-');
}

function seasonLabel(s) {
    return s && s.length === 8 ? `${s.slice(0,4)}–${s.slice(6)}` : (s || '-');
}

function displayBracket(data) {
    const slots = data.slots || [];
    const summary = data.summary || {};

    $('bracket-season').textContent = seasonLabel(data.season);
    $('bracket-correct').textContent = summary.scored ? `${summary.correct}/${summary.scored}` : '-';
    $('bracket-rate').textContent = summary.scored ? pct(summary.correct / summary.scored, 0) : '-';
    $('bracket-asof').textContent = data.state_as_of
        ? new Date(data.state_as_of + 'T12:00:00').toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric'})
        : '-';
    if (data.methodology) $('bracket-method').textContent = data.methodology;

    const west = slots.filter(s => s.conference === 'Western');
    const east = slots.filter(s => s.conference === 'Eastern');
    const final = slots.find(s => s.round === 4);

    // West runs inward left-to-right (R1→R3); East mirrors it, so its rounds
    // are laid out R3→R1 and every card is flipped to face the middle.
    const westCols = [1,2,3].map(r => renderRound(west.filter(s => s.round === r), r, 'west'));
    const eastCols = [3,2,1].map(r => renderRound(east.filter(s => s.round === r), r, 'east'));

    $('bracket-board').innerHTML =
        westCols.join('') +
        `<div class="bracket-col bracket-final-col">
            <div class="bracket-round-label"><span class="brl-conf">&nbsp;</span>Stanley Cup Final</div>
            <div class="bracket-col-body">
                <div class="bracket-cup">🏆</div>
                ${final ? renderSeries(final, 'final') : ''}
            </div>
        </div>` +
        eastCols.join('');

    renderTotals(data.final_totals || {});
}

function renderRound(series, round, side) {
    const labels = {1:'First Round', 2:'Second Round', 3:'Conference Final'};
    // The conference sits on its own line in every column header: once the
    // board wraps on a narrow screen, the left/right split that carries this
    // information on desktop is gone.
    const conf = side === 'west' ? 'West' : 'East';
    return `<div class="bracket-col bracket-col-r${round} ${side}">
        <div class="bracket-round-label"><span class="brl-conf ${side}">${conf}</span>${labels[round] || `Round ${round}`}</div>
        <div class="bracket-col-body">${series.map(s => renderSeries(s, side)).join('')}</div>
    </div>`;
}

function renderSeries(s, side) {
    const correct = !!s.correct;
    const mark = correct ? '✅' : '❌';
    const cls = correct ? 'bs-correct' : 'bs-wrong';
    const [a, b] = s.projected_matchup || ['?','?'];
    const prob = s.projected_winner_prob != null ? pct(s.projected_winner_prob, 0) : '';

    // Our projected matchup may never have happened — in later rounds the
    // teams we sent forward can differ from the teams that actually got there.
    const actualMatchup = (s.actual_matchup || []).join(' vs ');
    const projectedMatchup = [a, b].join(' vs ');
    const matchupDiffers = actualMatchup !== projectedMatchup;

    const teamRow = t => `<span class="bs-team${t === s.projected_winner ? ' bs-team-pick' : ''}">${t}</span>`;

    return `<div class="bracket-series ${side} ${cls}">
        <div class="bs-matchup">${teamRow(a)}<span class="bs-vs">vs</span>${teamRow(b)}</div>
        <div class="bs-verdict ${cls}">
            <span class="bs-mark">${mark}</span>
            <span class="bs-winner">${s.projected_winner || '—'}</span>
            <span class="bs-prob">${prob}</span>
        </div>
        <div class="bs-actual">
            ${s.actual_winner
                ? `Actual: <strong>${s.actual_winner}</strong> ${s.actual_result || ''}${matchupDiffers ? ` <span class="bs-actual-matchup">(${actualMatchup})</span>` : ''}`
                : 'Not played'}
        </div>
    </div>`;
}

function renderTotals(t) {
    if (!t || t.projected_series_total == null) {
        $('bracket-totals').innerHTML = `<div class="no-data"><p>No Final totals available.</p></div>`;
        return;
    }
    if (t.basis) $('totals-basis').textContent = `Projection basis: ${t.basis}.`;

    const diff = t.actual_series_total != null ? t.actual_series_total - t.projected_series_total : null;
    const diffCls = diff == null ? '' : Math.abs(diff) <= 4 ? 'total-green' : Math.abs(diff) <= 8 ? 'total-yellow' : 'total-red';

    $('bracket-totals').innerHTML = `
        <div class="totals-card">
            <div class="totals-label">We projected</div>
            <div class="totals-big">${t.projected_series_total.toFixed(1)}</div>
            <div class="totals-sub">${t.projected_per_game.toFixed(2)}/game × ${t.projected_games.toFixed(1)} games</div>
        </div>
        <div class="totals-card">
            <div class="totals-label">Actual</div>
            <div class="totals-big">${t.actual_series_total}</div>
            <div class="totals-sub">${t.actual_per_game != null ? t.actual_per_game.toFixed(2) : '—'}/game × ${t.actual_games} games</div>
        </div>
        <div class="totals-card">
            <div class="totals-label">Difference</div>
            <div class="totals-big ${diffCls}">${diff == null ? '—' : (diff > 0 ? '+' : '') + diff.toFixed(1)}</div>
            <div class="totals-sub">goals vs projection</div>
        </div>`;
}

// Model vs Vegas vs always picking the home team, in plain terms. Only games
// with a pre-game Vegas line count, so all three rows grade the same games.
const rec = (w, n) => `${w}-${n - w}`;
const tbl = rows => rows.map(([a, b, c, strong]) => `<div class="pred-result-row bench-row${strong ? ' bench-row--model' : ''}">
        <span class="pred-result-matchup">${a}</span>
        <span class="pred-result-winner">${b}</span>
        <span class="pred-result-winner"><span class="score">${c}</span></span>
    </div>`).join('');

function renderVegas(results) {
    const g = results.filter(r => r.market_pick);
    if (!g.length) {
        $('bench-table').innerHTML = `<p class="parlay-subtitle">No Vegas lines for these games. Odds are only recorded for live predictions (from the 2026-27 season on), not the backtest.</p>`;
        return;
    }
    const n = g.length;
    const modelW = g.filter(r => r.winner_correct).length;
    const vegasW = g.filter(r => r.market_correct).length;
    const homeW = g.filter(r => r.actual_winner === r.home).length;
    let h = tbl([
        ['Model', `record ${rec(modelW, n)}`, `${pct(modelW / n, 0)} right`, true],
        ['Vegas', `record ${rec(vegasW, n)}`, `${pct(vegasW / n, 0)} right`],
        ['Always pick the home team', `record ${rec(homeW, n)}`, 'the no-skill baseline'],
    ]);

    const diff = modelW - vegasW;
    const lines = [diff > 0 ? `So far the model has picked ${diff} more winner${diff > 1 ? 's' : ''} than Vegas.`
                : diff < 0 ? `So far Vegas has picked ${-diff} more winner${diff < -1 ? 's' : ''} than the model.`
                : 'So far the model and Vegas have picked the same number of winners.'];
    // Same floor scorecard.py uses before a model-vs-market gap means anything.
    if (n < 200) lines[0] += ` That is only ${n} game${n > 1 ? 's' : ''}, and hockey has lots of upsets, so it takes a few hundred games before the comparison really means something.`;
    const agree = g.filter(r => r.predicted_winner === r.market_pick).length;
    lines.push(`The model and Vegas picked the same team in ${pct(agree / n, 0)} of games.`);
    const dis = g.filter(r => r.predicted_winner !== r.market_pick);
    if (dis.length) {
        const disW = dis.filter(r => r.winner_correct).length;
        lines.push(`When they disagreed (${dis.length} game${dis.length > 1 ? 's' : ''}), the model was right ${disW} time${disW === 1 ? '' : 's'} and Vegas ${dis.length - disW}.`);
    }
    const t = g.filter(r => r.total_error != null && r.market_total_line != null);
    if (t.length) {
        const mMiss = t.reduce((a, r) => a + r.total_error, 0) / t.length;
        const vMiss = t.reduce((a, r) => a + Math.abs(r.market_total_line - r.actual_total), 0) / t.length;
        lines.push(`On total goals, the model missed by ${mMiss.toFixed(2)} on average; the Vegas over/under line missed by ${vMiss.toFixed(2)}.`);
    }
    if (n < results.length) lines.push(`${results.length - n} game${results.length - n > 1 ? 's' : ''} in this view had no Vegas line recorded and ${results.length - n > 1 ? 'are' : 'is'} left out of this comparison.`);
    h += lines.map(l => `<p class="parlay-subtitle" style="margin-top:10px">${l}</p>`).join('');
    $('bench-table').innerHTML = h;
}

function displayNoPerformanceData(msg) {
    $('bench-table').innerHTML = '';
    $('recent-results-list').innerHTML = `<div class="no-data"><div class="no-data-icon">📊</div><p>${msg || 'No performance data yet.'}</p></div>`;
    ['perf-total-bets','perf-win-rate','perf-total-exact','perf-total-within1'].forEach(id => $(id).textContent = '-');
    ['total-green','total-yellow','total-red'].forEach(id => $(id).textContent = '0');
}

(function(){
    const b = document.createElement('button'); b.className = 'scroll-top-btn'; b.innerHTML = '↑'; b.setAttribute('aria-label', 'Scroll to top');
    b.addEventListener('click', () => window.scrollTo({top:0, behavior:'smooth'}));
    document.body.appendChild(b);
    window.addEventListener('scroll', () => b.classList.toggle('visible', window.scrollY > 400), {passive:true});
})();

loadAnalysis();
setInterval(loadAnalysis, 3e5);
