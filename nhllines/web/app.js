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
        el.innerHTML = `<p>⚠️ Could not load prediction data. Make sure latest_analysis.json is available.</p>`;
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

    const strong = allRecommendations.filter(r => r.confidence >= 0.60);
    $('bets-found').textContent = strong.length;

    if (allRecommendations.length) {
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

    return `<div class="gc${isStrong?' gc-strong':''}" id="gc-${i}">
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
                <span class="gc-total-unit">exp. goals</span>
                ${totalLine ? `<span class="gc-line">Line ${totalLine}${ouHtml}</span>` : ''}
            </div>
            <div class="gc-conf">
                <span class="gc-conf-label">Conf</span>
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
        const predicted = Math.round(r.predicted_total);
        const parts = r.actual_score?.split('-') || [];
        const score = parts.length === 2 ? `${parts[0]}–${parts[1]}` : '';
        const d = new Date(r.date + 'T12:00:00');
        const dateStr = d.toLocaleDateString('en-US', {month:'short', day:'numeric'});
        return `<div class="pred-result-row">
            <span class="pred-result-date">${dateStr}</span>
            <span class="pred-result-matchup">${r.game}</span>
            <span class="pred-result-winner">${winIcon} ${r.predicted_winner}${score ? `<span class="score"> ${score}</span>` : ''}</span>
            <span class="pred-result-total ${cls}">${dot} ${predicted}<span class="actual"> · ${r.actual_total}</span></span>
        </div>`;
    }).join('');
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
