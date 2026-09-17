let allGames = [], allRecommendations = [];

const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);
const pct = (v, d=1) => (v*100).toFixed(d) + '%';

function getGrade(conf) { return conf>=.75?'A':conf>=.60?'B+':conf>=.50?'B':'C+'; }
function getGradeClass(g) { return {A:'grade-a','B+':'grade-b-plus',B:'grade-b','C+':'grade-c-plus'}[g]||'grade-c-plus'; }

function showTab(t) {
    ['today-tab','performance-tab'].forEach(id => { if($(id)) $(id).style.display='none'; });
    $$('.tab-button').forEach(b => b.classList.remove('active'));
    if (t === 'today') {
        $('today-tab').style.display = 'block';
        $$('.tab-button')[0].classList.add('active');
    } else {
        $('performance-tab').style.display = 'block';
        $$('.tab-button')[1].classList.add('active');
        loadPerformanceData();
    }
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
        el.innerHTML = `<p>Could not load prediction data. Make sure latest_analysis.json is available.</p>`;
    }
}

async function loadPerformanceData() {
    try {
        const r = await fetch(`backtest_results.json?v=${Date.now()}`);
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

    const pickProb = g => g.model_probs?.confidence || 0;
    $('bets-found').textContent = allGames.filter(g => pickProb(g) >= 0.60).length;

    if (allGames.length) {
        const avgConf = allGames.reduce((s, g) => s + pickProb(g), 0) / allGames.length;
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
        games = games.filter(g => (g.model_probs?.confidence || 0) >= 0.60);
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
        container.innerHTML = `<div class="no-data"><div class="no-data-icon">⚾</div><p>No games found.</p></div>`;
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

    const overProb = mp.over_prob;
    const topConf = conf;
    const isStrong = topConf >= 0.60;
    const grade = isStrong ? getGrade(topConf) : null;
    const gradeClass = grade ? getGradeClass(grade) : '';

    let ouHtml = '';
    if (totalLine && overProb != null && Math.abs(overProb - 0.5) >= 0.05) {
        const isOver = overProb > 0.5;
        ouHtml = ` · <span class="gc-ou ${isOver?'over':'under'}">${isOver?'↑ Over':'↓ Under'} ${(Math.max(overProb,1-overProb)*100).toFixed(0)}%</span>`;
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
                <span class="gc-total-unit">exp. runs</span>
                ${totalLine ? `<span class="gc-line">Line ${totalLine}${ouHtml}</span>` : ''}
                ${g.market_probs ? `<span class="gc-line">Market ${g.home} ${(g.market_probs.home_win_prob*100).toFixed(0)}%</span>` : ''}
            </div>
            <div class="gc-conf">
                <span class="gc-conf-label">Pick</span>
                <div class="confidence-bar gc-conf-bar"><div class="confidence-fill" style="width:${confPct}%"></div></div>
                <span class="gc-conf-pct">${confPct}%</span>
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
    (ci.pitcher||[]).forEach(i => { const icon = i.type==='ace'?'🔥':i.type==='tbd'?'❔':'⚠️'; const t = i.type==='ace'?'Ace':i.type==='tbd'?'SP TBD':'Weak SP'; b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${icon}</span>${i.team} ${t}</span>`); });
    (ci.park||[]).forEach(i => { const icon = i.type==='hitter-friendly'?'🏟️':'⚾'; b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${icon}</span>${i.type}</span>`); });
    (ci.splits||[]).forEach(i => { const t={strong_home:'Strong Home',weak_home:'Weak Home',strong_road:'Strong Road',weak_road:'Weak Road'}[i.type]; if(t) b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${i.severity==='positive'?'🏠':'🛣️'}</span>${i.team} ${t}</span>`); });
    return b.length ? `<div class="context-indicators">${b.join('')}</div>` : '';
}

function renderGameDetails(g) {
    let h = '';
    const pm = g.pitcher_matchup;
    if (pm?.home && pm?.away) {
        const pc = (t, label) => `<div class="goalie-card">
            <div class="goalie-name">${label}: ${t.name} (${t.handedness}HP)</div>
            <div class="goalie-stats">
                <div class="goalie-stat-row"><span class="goalie-stat-label">Model FIP</span><span class="goalie-stat-value">${t.fip.toFixed(2)}</span></div>
                <div class="goalie-stat-row"><span class="goalie-stat-label">K-BB%</span><span class="goalie-stat-value">${t.k_bb_pct != null ? t.k_bb_pct.toFixed(1) : '-'}</span></div>
                <div class="goalie-stat-row"><span class="goalie-stat-label">Season ERA</span><span class="goalie-stat-value">${t.era.toFixed(2)}</span></div>
                <div class="goalie-stat-row"><span class="goalie-stat-label">WHIP</span><span class="goalie-stat-value">${t.whip.toFixed(2)}</span></div>
            </div>
            <div class="quality-score">${t.quality_score.toFixed(0)}</div>
        </div>`;
        h += `<div class="details-section"><h3>Pitcher Matchup</h3><div class="goalie-comparison">${pc(pm.home, g.home)}${pc(pm.away, g.away)}</div></div>`;
    }
    const sp = g.team_splits;
    if (sp?.home && sp?.away) {
        const sc = (lbl, d) => `<div class="split-card">
            <div class="split-title">${lbl}</div>
            <div class="split-stats">
                <div class="split-stat-row"><span class="split-stat-label">Win %</span><span class="split-stat-value">${pct(d.win_pct||0)}</span></div>
                <div class="split-stat-row"><span class="split-stat-label">RS/G</span><span class="split-stat-value">${(d.rs_pg||0).toFixed(2)}</span></div>
                <div class="split-stat-row"><span class="split-stat-label">RA/G</span><span class="split-stat-value">${(d.ra_pg||0).toFixed(2)}</span></div>
            </div>
        </div>`;
        h += `<div class="details-section"><h3>Home/Road Splits (L10)</h3><div class="splits-comparison">${sc(g.home + ' at Home', sp.home)}${sc(g.away + ' on Road', sp.away)}</div></div>`;
    }
    if (g.bullpen?.home && g.bullpen?.away) {
        h += `<div class="details-section"><h3>Bullpen Quality</h3><div class="advanced-stats-grid">
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.home} BP RA/9</div><div class="advanced-stat-value">${(g.bullpen.home.bullpen_ra9||4.5).toFixed(2)}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.away} BP RA/9</div><div class="advanced-stat-value">${(g.bullpen.away.bullpen_ra9||4.5).toFixed(2)}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.home} Quality</div><div class="advanced-stat-value">${(g.bullpen.home.bullpen_quality||50).toFixed(0)}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.away} Quality</div><div class="advanced-stat-value">${(g.bullpen.away.bullpen_quality||50).toFixed(0)}</div></div>
        </div></div>`;
    }
    if (g.park_factor) {
        const mk = g.market_probs;
        h += `<div class="details-section"><h3>Model vs Market</h3><div class="advanced-stats-grid">
            <div class="advanced-stat-card"><div class="advanced-stat-label">Model ${g.home}</div><div class="advanced-stat-value">${pct(g.model_probs.home_win_prob)}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">Market ${g.home}</div><div class="advanced-stat-value">${mk ? pct(mk.home_win_prob) : '-'}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">Elo ${g.away} / ${g.home}</div><div class="advanced-stat-value">${g.elo ? `${g.elo.away} / ${g.elo.home}` : '-'}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.home} Park (100 = avg)</div><div class="advanced-stat-value">${g.park_factor}</div></div>
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
    $('perf-total-within1').textContent = (data.within_1_run ?? data.within_1_goal) != null ? pct(data.within_1_run ?? data.within_1_goal) : '-';
    $('perf-total-exact').textContent = data.avg_total_error != null ? data.avg_total_error.toFixed(2) : '-';
    renderBenchmarks(data);

    const diffs = results.map(r => Math.abs(Math.round(r.predicted_total) - r.actual_total));
    const greenCount = diffs.filter(d => d === 0).length;
    const yellowCount = diffs.filter(d => d === 1).length;
    const redCount = diffs.filter(d => d >= 2).length;

    $('total-green').textContent = greenCount;
    $('total-yellow').textContent = yellowCount;
    $('total-red').textContent = redCount;
    $('total-green-pct').textContent = pct(greenCount / n);
    $('total-yellow-pct').textContent = pct(yellowCount / n);
    $('total-red-pct').textContent = pct(redCount / n);

    $('recent-results-list').innerHTML = results.slice(0, 60).map(r => {
        const diff = Math.abs(Math.round(r.predicted_total) - r.actual_total);
        const dot = diff === 0 ? '🟢' : diff === 1 ? '🟡' : '🔴';
        const cls = diff === 0 ? 'total-green' : diff === 1 ? 'total-yellow' : 'total-red';
        const winIcon = r.winner_correct ? '✅' : '❌';
        const pickProb = r.confidence != null ? ` ${(r.confidence*100).toFixed(0)}%` : '';
        const predicted = Math.round(r.predicted_total);
        const parts = r.actual_score?.split('-') || [];
        const score = parts.length === 2 ? `${parts[0]}–${parts[1]}` : '';
        const d = new Date(r.date + 'T12:00:00');
        const dateStr = d.toLocaleDateString('en-US', {month:'short', day:'numeric'});
        return `<div class="pred-result-row">
            <span class="pred-result-date">${dateStr}</span>
            <span class="pred-result-matchup">${r.game}</span>
            <span class="pred-result-winner">${winIcon} ${r.predicted_winner}${pickProb}${score ? `<span class="score"> ${score}</span>` : ''}</span>
            <span class="pred-result-total ${cls}">${dot} ${predicted}<span class="actual"> · ${r.actual_total}</span></span>
        </div>`;
    }).join('');
}

function renderBenchmarks(data) {
    const el = $('bench-table');
    if (!el) return;
    const b = data.benchmarks, mc = data.market_comparison;
    if (!b) { el.innerHTML = ''; return; }
    // Three cells, not four: dashboard.css hides .pred-result-total on phones,
    // and log loss is the number this table exists to show.
    const row = (label, m, strong) => m && m.n ? `<div class="pred-result-row bench-row${strong?' bench-row--model':''}">
            <span class="pred-result-matchup">${label}<span class="pred-result-date"> · ${m.n}</span></span>
            <span class="pred-result-winner">${pct(m.accuracy)}</span>
            <span class="pred-result-winner">LL ${m.log_loss.toFixed(4)}<span class="score"> · Brier ${m.brier.toFixed(4)}</span></span>
        </div>` : '';
    let h = row('This model', b.model, true) + row('Elo + home field', b.elo) + row('Always pick home', b.always_home);
    if (mc && mc.n) {
        h += `<p class="parlay-subtitle" style="margin-top:12px">Same games where a pre-game market price was archived${mc.n < 200 ? ' (under 200 games, so the gap is noise)' : ''}:</p>`;
        h += row('This model', mc.model, true) + row('Market close', mc.market);
    }
    if (data.season) $('bench-note').textContent = `Blind ${data.season} season: models trained on ${(data.trained_on_seasons||[]).join(', ')} only. Lower log loss and Brier are better; accuracy alone rewards overconfidence.`;
    el.innerHTML = h;
}

function displayNoPerformanceData() {
    $('recent-results-list').innerHTML = `<div class="no-data"><div class="no-data-icon">📊</div><p>No performance data yet. Run backtest.py to generate.</p></div>`;
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
