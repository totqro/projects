let allGames = [], allRecommendations = [];

const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);
const pct = (v, d=1) => (v*100).toFixed(d) + '%';

function getGrade(conf) { return conf>=.75?'A':conf>=.60?'B+':conf>=.50?'B':'C+'; }
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

async function loadPerformanceData() {
    try {
        const r = await fetch(`performance_history.json?v=${Date.now()}`);
        if (!r.ok) { displayNoPerformanceData(); return; }
        displayPerformance(await r.json());
    } catch(e) { console.error(e); displayNoPerformanceData(); }
}

function displayAnalysis(data) {
    const ts = new Date(data.timestamp);
    $('timestamp').textContent = ts.toLocaleString('en-US', {month:'short', day:'numeric', hour:'numeric', minute:'2-digit', timeZone:'America/New_York'}) + ' EST';
    $('games-analyzed').textContent = data.games_analyzed.length;

    allGames = data.games_analyzed;
    allRecommendations = data.recommendations;

    const strong = allRecommendations.filter(r => r.confidence >= 0.60);
    $('bets-found').textContent = strong.length;

    const preseason = allGames.length > 0 && allGames.every(g => g.game_type === 1);
    $('preseason-banner').style.display = preseason ? 'block' : 'none';
    // Every preseason game has 0 confidence, so that sort would be arbitrary.
    if (preseason && $('sort-games').value === 'confidence') $('sort-games').value = 'prob';

    if (preseason) {
        // Preseason: no picks are made, so "confidence" has nothing to average.
        $('expected-roi').textContent = 'N/A';
    } else if (allRecommendations.length) {
        const avgConf = allRecommendations.reduce((s, b) => s + (b.confidence||0), 0) / allRecommendations.length;
        $('expected-roi').textContent = pct(avgConf, 0);
    } else {
        $('expected-roi').textContent = 'N/A';
    }

    applySort();
}

function applySort() {
    const sortBy = $('sort-games')?.value || 'confidence';
    const strongOnly = $('strong-only')?.checked || false;

    const recsByGame = {};
    allRecommendations.forEach(r => {
        if (!recsByGame[r.game]) recsByGame[r.game] = [];
        recsByGame[r.game].push(r);
    });

    let games = [...allGames];

    if (strongOnly) {
        const strongGames = new Set(
            allRecommendations.filter(r => r.confidence >= 0.60).map(r => r.game)
        );
        games = games.filter(g => strongGames.has(g.game));
    }

    if (sortBy === 'confidence') {
        games.sort((a, b) => {
            const ca = Math.max(...(recsByGame[a.game]||[]).map(r => r.confidence||0), (a.blended_probs||a.model_probs)?.confidence||0);
            const cb = Math.max(...(recsByGame[b.game]||[]).map(r => r.confidence||0), (b.blended_probs||b.model_probs)?.confidence||0);
            return cb - ca;
        });
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
    const conf = bp.confidence || mp.confidence || 0;
    const isPre = g.game_type === 1;

    const totalRec = gameRecs.find(r => r.bet_type === 'Total');
    const topConf = gameRecs.length ? Math.max(...gameRecs.map(r => r.confidence||0)) : 0;
    const isStrong = topConf >= 0.60;
    const grade = isStrong ? getGrade(topConf) : null;
    const gradeClass = grade ? getGradeClass(grade) : '';

    let ouHtml = '';
    if (totalRec && totalLine) {
        const isOver = (totalRec.pick||'').toLowerCase().startsWith('over');
        ouHtml = ` · <span class="gc-ou ${isOver?'over':'under'}">${isOver?'↑ Over':'↓ Under'}</span>`;
    }

    const homePct = (homeProb*100).toFixed(0);
    const awayPct = (awayProb*100).toFixed(0);
    const confPct = (conf*100).toFixed(0);
    const homeWins = homeProb > awayProb;
    const contextHtml = renderContextIndicators(ci);

    return `<div class="gc cy-panel${isStrong?' gc-strong':''}" id="gc-${i}">
        <div class="gc-header" onclick="toggleGC(${i})">
            <div class="gc-matchup">
                <span class="${!homeWins?'gc-pick-team':''}">${g.away}</span>
                <span class="gc-sep">@</span>
                <span class="${homeWins?'gc-pick-team':''}">${g.home}</span>
            </div>
            ${grade ? `<span class="grade ${gradeClass} gc-grade">${grade}</span>` : ''}
            ${isPre ? `<span class="cy-badge gc-pre">Preseason</span>` : ''}
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
            ${isPre
                ? `<div class="gc-conf"><span class="gc-conf-label">${g.win_model === 'elo' ? 'Elo rating' : 'xG model'} · low-info</span></div>`
                : `<div class="gc-conf">
                <span class="gc-conf-label">Conf</span>
                <div class="confidence-bar gc-conf-bar"><div class="confidence-fill" style="width:${confPct}%"></div></div>
                <span class="gc-conf-pct">${confPct}%</span>
            </div>`}
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

let perfPeriods = [], perfCurrent = null, perfShowAll = false;
const PERF_PAGE = 60;

function displayPerformance(data) {
    perfPeriods = data?.periods || [];
    if (!perfPeriods.length) { displayNoPerformanceData(); return; }

    // Periods arrive newest season first; group them by season in the picker.
    const bySeason = [];
    perfPeriods.forEach(p => {
        let grp = bySeason.find(g => g.season === p.season);
        if (!grp) { grp = { season: p.season, label: p.label, items: [] }; bySeason.push(grp); }
        grp.items.push(p);
    });
    $('perf-period').innerHTML = bySeason.map(g =>
        `<optgroup label="${g.label} season">${g.items.map(p =>
            `<option value="${p.id}">${p.label} · ${p.phase_label}${p.status === 'in_progress' ? ' (live)' : ''}</option>`
        ).join('')}</optgroup>`
    ).join('');

    // Land on the newest period that has something scored; an empty period
    // (a season that has only just started) stays one click away.
    const initial = perfPeriods.find(p => p.n_games > 0) || perfPeriods[0];
    $('perf-period').value = initial.id;
    selectPeriod(initial.id);
}

function selectPeriod(id) {
    const p = perfPeriods.find(x => x.id === id);
    if (!p) return;
    perfCurrent = p;
    perfShowAll = false;
    renderPeriod(p);
}

function showAllPerf() { perfShowAll = true; renderPeriod(perfCurrent); }

function renderPeriod(p) {
    const win = p.win || {}, totals = p.totals || {};
    const done = p.games.filter(g => g.home_win !== null);
    const n = done.length;

    $('perf-status').textContent = p.status === 'in_progress' ? '· live' : '';
    $('perf-note').textContent = p.note || '';
    $('perf-total-bets').textContent = n;
    $('perf-win-rate').textContent = win.accuracy != null ? pct(win.accuracy) : '-';
    $('perf-log-loss').textContent = win.log_loss != null ? win.log_loss.toFixed(4) : '-';
    $('perf-total-exact').textContent = totals.mae != null ? totals.mae.toFixed(2) : '-';

    // Log loss only means something next to a reference: 0.6931 is a coin flip.
    const bench = [];
    if (win.log_loss != null) {
        bench.push('coin flip 0.6931');
        const elo = p.benchmarks?.elo;
        if (elo?.log_loss != null) bench.push(`Elo baseline ${elo.log_loss.toFixed(4)}`);
        const m = p.benchmarks?.market;
        if (m?.market?.log_loss != null) {
            bench.push(`market closing line ${m.market.log_loss.toFixed(4)} (model ${m.model.log_loss.toFixed(4)} on the same ${p.benchmarks.market_n} games`
                + `${p.benchmarks.market_meaningful ? '' : ' — too few to call'})`);
        }
        $('perf-bench').textContent = 'Lower log loss is better. Reference: ' + bench.join(' · ') + '.';
    } else {
        $('perf-bench').textContent = '';
    }

    const diffs = done.filter(g => g.pred_total != null).map(g => Math.abs(Math.round(g.pred_total) - g.total_goals));
    const dn = diffs.length;
    const green = diffs.filter(d => d === 0).length;
    const yellow = diffs.filter(d => d === 1).length;
    const red = diffs.filter(d => d >= 2).length;
    $('total-green').textContent = green;
    $('total-yellow').textContent = yellow;
    $('total-red').textContent = red;
    $('total-green-pct').textContent = dn ? pct(green / dn) : '';
    $('total-yellow-pct').textContent = dn ? pct(yellow / dn) : '';
    $('total-red-pct').textContent = dn ? pct(red / dn) : '';

    const shown = perfShowAll ? p.games : p.games.slice(0, PERF_PAGE);
    $('perf-list-count').textContent = shown.length < p.games.length
        ? `latest ${shown.length} of ${p.games.length}` : `${p.games.length} games`;
    const more = $('perf-show-all');
    more.style.display = shown.length < p.games.length ? 'inline-flex' : 'none';
    more.textContent = `Show all ${p.games.length} games`;

    if (!p.games.length) { displayNoPerformanceData('No games in this period yet.'); return; }

    $('recent-results-list').innerHTML = shown.map(g => {
        const pickHome = g.p_home > 0.5;
        const pick = pickHome ? g.home : g.away;
        const pickProb = pickHome ? g.p_home : 1 - g.p_home;
        const d = new Date(g.date + 'T12:00:00');
        const dateStr = d.toLocaleDateString('en-US', {month:'short', day:'numeric'});
        const isDone = g.home_win !== null;
        const correct = isDone && (g.home_win === 1) === pickHome;
        const winIcon = !isDone ? '⏳' : correct ? '✅' : '❌';
        const winner = isDone ? (g.home_win === 1 ? g.home : g.away) : null;

        let totalHtml = `<span class="pred-result-total">${g.pred_total != null ? Math.round(g.pred_total) : '—'}<span class="actual"> · —</span></span>`;
        if (isDone && g.pred_total != null) {
            const diff = Math.abs(Math.round(g.pred_total) - g.total_goals);
            const dot = diff === 0 ? '🟢' : diff === 1 ? '🟡' : '🔴';
            const cls = diff === 0 ? 'total-green' : diff === 1 ? 'total-yellow' : 'total-red';
            totalHtml = `<span class="pred-result-total ${cls}">${dot} ${Math.round(g.pred_total)}<span class="actual"> · ${g.total_goals}</span></span>`;
        }
        return `<div class="pred-result-row">
            <span class="pred-result-date">${dateStr}</span>
            <span class="pred-result-matchup">${g.away} @ ${g.home}</span>
            <span class="pred-result-winner">${winIcon} ${pick} ${pct(pickProb, 0)}${winner ? `<span class="score"> ${winner} won</span>` : ''}</span>
            ${totalHtml}
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

function displayNoPerformanceData(msg) {
    $('recent-results-list').innerHTML = `<div class="no-data"><div class="no-data-icon">📊</div><p>${msg || 'No performance data yet. Run performance_history.py to generate.'}</p></div>`;
    if (!msg) {
        ['perf-total-bets','perf-win-rate','perf-total-exact','perf-log-loss'].forEach(id => $(id).textContent = '-');
        ['total-green','total-yellow','total-red'].forEach(id => $(id).textContent = '0');
        $('perf-note').textContent = '';
        $('perf-bench').textContent = '';
    }
}

(function(){
    const b = document.createElement('button'); b.className = 'scroll-top-btn'; b.innerHTML = '↑'; b.setAttribute('aria-label', 'Scroll to top');
    b.addEventListener('click', () => window.scrollTo({top:0, behavior:'smooth'}));
    document.body.appendChild(b);
    window.addEventListener('scroll', () => b.classList.toggle('visible', window.scrollY > 400), {passive:true});
})();

loadAnalysis();
setInterval(loadAnalysis, 3e5);
