let allRecommendations = [], allOddsData = {}, filtersSetUp = false;
let currentFilters = { grade:'all', type:'all', sortBy:'confidence' };

// Helpers
const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);
const pct = (v,d=1) => (v*100).toFixed(d)+'%';

function getGrade(conf) { return conf>=.75?'A':conf>=.60?'B+':conf>=.50?'B':'C+'; }
function getGradeClass(g) { return {A:'grade-a','B+':'grade-b-plus',B:'grade-b','C+':'grade-c-plus'}[g]||'grade-c-plus'; }

// Tabs
function showTab(t) {
    ['today-tab','performance-tab','backtest-tab'].forEach(id => { if($(id)) $(id).style.display='none'; });
    $$('.tab-button').forEach(b => b.classList.remove('active'));
    if (t==='today') { $('today-tab').style.display='block'; $$('.tab-button')[0].classList.add('active'); }
    else if (t==='performance') { $('performance-tab').style.display='block'; $$('.tab-button')[1].classList.add('active'); loadPerformanceData(); }
    else if (t==='backtest') { $('backtest-tab').style.display='block'; $$('.tab-button')[2].classList.add('active'); loadBacktestData(); }
}

// Data loading
async function loadAnalysis() {
    try {
        const r = await fetch(`latest_analysis.json?v=${Date.now()}`);
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        displayAnalysis(await r.json());
        $('loading').style.display='none';
        showTab('today');
    } catch(e) {
        console.error(e);
        $('loading').style.display='none';
        const el=$('error'); el.style.display='block';
        el.innerHTML=`<p>Error: ${e.message}</p>`;
    }
}

async function loadPerformanceData() {
    try {
        const r = await fetch(`bet_results.json?v=${Date.now()}`);
        displayPerformance(r.ok ? await r.json() : null);
    } catch(e) { console.error(e); displayNoPerformanceData(); }
}

async function loadBacktestData() {
    const list = $('backtest-list');
    if (!list) return;
    try {
        const r = await fetch(`backtest_results.json?v=${Date.now()}`);
        if (!r.ok) { list.innerHTML='<p class="no-data">No backtest data yet. Run backtest.py to generate results.</p>'; return; }
        const d = await r.json();
        $('bt-total').textContent = d.total_games ?? '-';
        $('bt-winner-acc').textContent = d.winner_accuracy != null ? pct(d.winner_accuracy) : '-';
        $('bt-avg-error').textContent = d.avg_total_error != null ? d.avg_total_error.toFixed(2) + ' runs' : '-';
        $('bt-within1').textContent = d.within_1_run != null ? pct(d.within_1_run) : '-';
        if ($('backtest-date-range') && d.start_date) $('backtest-date-range').textContent = `since ${d.start_date}`;
        if (!d.results?.length) { list.innerHTML='<p class="no-data">No game results in backtest data.</p>'; return; }
        list.innerHTML = d.results.map(r => {
            const icon = r.winner_correct ? '✅' : '❌';
            const errColor = r.total_error <= 1 ? '#22c55e' : r.total_error <= 2 ? '#eab308' : '#ef4444';
            return `<div class="result-item">
                <div class="result-header">
                    <span class="result-game">${icon} ${r.game}</span>
                    <span class="result-date">${r.date}</span>
                </div>
                <div class="result-details">
                    <span>Pred winner: <strong>${r.predicted_winner}</strong> (${pct(r.predicted_home_win_prob)} home)</span>
                    <span>Actual: <strong>${r.actual_winner}</strong> ${r.actual_score}</span>
                    <span>Total: pred <strong>${r.predicted_total?.toFixed(1)}</strong> / actual <strong>${r.actual_total}</strong>
                        <span style="color:${errColor};">(±${r.total_error?.toFixed(1)})</span></span>
                </div>
            </div>`;
        }).join('');
    } catch(e) { console.error(e); list.innerHTML='<p class="no-data">Could not load backtest data.</p>'; }
}

// Total runs difference helper
function getTotalDiff(r) {
    const actual = r.game_result?.total;
    if (actual == null) return null;
    const match = (r.bet.pick||'').match(/(?:Over|Under)\s+([\d.]+)/i);
    if (!match) return null;
    const predicted = Math.round(parseFloat(match[1]));
    return Math.abs(predicted - actual);
}

function getTotalColor(diff) {
    if (diff === null) return '';
    if (diff === 0) return 'total-green';
    if (diff === 1) return 'total-yellow';
    return 'total-red';
}

function getTotalDot(diff) {
    if (diff === null) return '';
    if (diff === 0) return '🟢';
    if (diff === 1) return '🟡';
    return '🔴';
}

function displayPerformance(results) {
    if (!results?.results || !Object.keys(results.results).length) { displayNoPerformanceData(); return; }
    const allBets = Object.values(results.results).filter(r => r.result !== 'push');

    // Deduplicate ML bets by game (highest confidence per game)
    const mlByGame = {};
    allBets.filter(r => r.bet.bet_type === 'Moneyline').forEach(r => {
        const key = `${r.game_result?.date}_${r.bet.game}`;
        if (!mlByGame[key] || (r.bet.confidence||0) > (mlByGame[key].bet.confidence||0)) mlByGame[key] = r;
    });

    // Deduplicate Total bets by game
    const totalByGame = {};
    allBets.filter(r => r.bet.bet_type === 'Total').forEach(r => {
        const key = `${r.game_result?.date}_${r.bet.game}`;
        if (!totalByGame[key] || (r.bet.confidence||0) > (totalByGame[key].bet.confidence||0)) totalByGame[key] = r;
    });

    const mlGames = Object.values(mlByGame);
    const totalGames = Object.values(totalByGame);

    const correctWinner = mlGames.filter(r => r.result === 'won');

    const diffs = totalGames.map(r => getTotalDiff(r)).filter(v => v !== null);
    const greenCount = diffs.filter(d => d === 0).length;
    const yellowCount = diffs.filter(d => d === 1).length;
    const redCount = diffs.filter(d => d >= 2).length;
    const totalTracked = diffs.length;

    const trackedGames = Math.max(mlGames.length, totalGames.length);
    $('perf-total-bets').textContent = trackedGames;
    $('perf-win-rate').textContent = mlGames.length ? pct(correctWinner.length / mlGames.length) : '-';
    $('perf-total-exact').textContent = totalTracked ? pct(greenCount / totalTracked) : '-';
    $('perf-total-within1').textContent = totalTracked ? pct((greenCount + yellowCount) / totalTracked) : '-';

    $('total-green').textContent = greenCount;
    $('total-yellow').textContent = yellowCount;
    $('total-red').textContent = redCount;
    $('total-green-pct').textContent = totalTracked ? pct(greenCount/totalTracked) : '';
    $('total-yellow-pct').textContent = totalTracked ? pct(yellowCount/totalTracked) : '';
    $('total-red-pct').textContent = totalTracked ? pct(redCount/totalTracked) : '';

    displayRecentResults(allBets);
}

function displayRecentResults(bets) {
    const gameMap = {};
    bets.forEach(r => {
        const key = `${r.game_result?.date}_${r.bet.game}`;
        if (!gameMap[key]) gameMap[key] = { game: r.bet.game, date: r.game_result?.date, ts: r.bet.analysis_timestamp, ml: null, total: null };
        if (r.bet.bet_type === 'Moneyline' && (!gameMap[key].ml || (r.bet.confidence||0) > (gameMap[key].ml.bet.confidence||0)))
            gameMap[key].ml = r;
        if (r.bet.bet_type === 'Total' && (!gameMap[key].total || (r.bet.confidence||0) > (gameMap[key].total.bet.confidence||0)))
            gameMap[key].total = r;
    });

    const sorted = Object.values(gameMap).sort((a,b) => new Date(b.ts||b.date+'T12:00:00') - new Date(a.ts||a.date+'T12:00:00'));

    $('recent-results-list').innerHTML = sorted.slice(0,30).map(g => {
        const gr = g.ml, gt = g.total;
        const d = new Date(g.ts || (g.date+'T12:00:00'));
        const dateStr = d.toLocaleDateString('en-US',{month:'short',day:'numeric'});

        let winnerHtml = '<span class="pred-result-winner" style="color:var(--t3)">—</span>';
        if (gr) {
            const icon = gr.result === 'won' ? '✅' : '❌';
            const pick = gr.bet.pick.replace(/ ML$/i,'');
            const gr2 = gr.game_result;
            const parts = gr.bet.game.split(' @ ');
            const away = parts[0], home = parts[1]||'';
            const score = gr2?.home_score != null ? `${gr2.away_score}–${gr2.home_score}` : '';
            winnerHtml = `<span class="pred-result-winner">${icon} ${pick}${score?`<span class="score">${score}</span>`:''}</span>`;
        }

        let totalHtml = '<span class="pred-result-total" style="color:var(--t3)">—</span>';
        if (gt) {
            const diff = getTotalDiff(gt);
            const dot = getTotalDot(diff);
            const cls = getTotalColor(diff);
            const match = (gt.bet.pick||'').match(/(?:Over|Under)\s+([\d.]+)/i);
            const predicted = match ? Math.round(parseFloat(match[1])) : null;
            const actual = gt.game_result?.total;
            if (predicted != null) {
                const actualStr = actual != null ? ` · ${actual}` : '';
                totalHtml = `<span class="pred-result-total ${cls}">${dot} ${predicted}<span class="actual">${actualStr}</span></span>`;
            }
        }

        return `<div class="pred-result-row">
            <span class="pred-result-date">${dateStr}</span>
            <span class="pred-result-matchup">${g.game}</span>
            ${winnerHtml}
            ${totalHtml}
        </div>`;
    }).join('');
}

function displayNoPerformanceData() {
    $('recent-results-list').innerHTML = `<div class="no-data"><div class="no-data-icon">📊</div><p>No performance data yet.</p></div>`;
    ['perf-total-bets','perf-win-rate','perf-total-exact','perf-total-within1'].forEach(id => $(id).textContent = '-');
    ['total-green','total-yellow','total-red'].forEach(id => $(id).textContent = '0');
}

// Analysis display
function displayAnalysis(data) {
    const ts = new Date(data.timestamp);
    $('timestamp').textContent = ts.toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZone:'America/New_York'})+' EST';
    $('games-analyzed').textContent = data.games_analyzed.length;
    $('bets-found').textContent = data.recommendations.length;

    if (data.recommendations.length) {
        const avgConf = data.recommendations.reduce((s,b) => s + (b.confidence||0), 0) / data.recommendations.length;
        $('expected-roi').textContent = pct(avgConf, 0);
    } else {
        $('expected-roi').textContent = 'N/A';
    }

    allRecommendations = data.recommendations;
    allOddsData = data.all_odds || {};
    setupFilters();
    displayRecommendations(allRecommendations);
    displayGames(data.games_analyzed);
}

// Filters
function setupFilters() {
    if (filtersSetUp) return; filtersSetUp = true;
    ['filter-grade','filter-type','sort-by'].forEach(id => {
        $(id).addEventListener('change', e => {
            currentFilters[{['filter-grade']:'grade',['filter-type']:'type',['sort-by']:'sortBy'}[id]] = e.target.value;
            applyFilters();
        });
    });
}

function applyFilters() {
    let f = [...allRecommendations];
    if (currentFilters.grade !== 'all') f = f.filter(b => getGrade(b.confidence||0) === currentFilters.grade);
    if (currentFilters.type !== 'all') f = f.filter(b => b.bet_type === currentFilters.type);

    const sorts = {
        confidence: (a,b) => (b.confidence||0) - (a.confidence||0),
        prob: (a,b) => Math.abs(b.true_prob - 0.5) - Math.abs(a.true_prob - 0.5),
    };
    f.sort(sorts[currentFilters.sortBy] || sorts.confidence);

    $('bets-found').textContent = f.length;
    displayRecommendations(f);
}

// Prediction card rendering
function compactStat(label,val,cls='') { return `<div class="compact-stat"><span class="compact-stat-label">${label}</span><span class="compact-stat-value ${cls}">${val}</span></div>`; }
function predMetric(label,val,cls='') { return `<div class="key-metric"><div class="key-metric-label">${label}</div><div class="key-metric-value ${cls}">${val}</div></div>`; }
function detailInline(label,val) { return `<div class="detail-item-inline"><span class="detail-label">${label}</span><span class="detail-value">${val}</span></div>`; }

function displayRecommendations(recs) {
    const c = $('recommendations-list');
    if (!recs.length) {
        c.innerHTML = `<div class="no-data" style="padding:24px"><p style="color:var(--text-muted)">No predictions match your criteria.</p></div>`;
        return;
    }
    const compact = $('view-toggle')?.dataset.view === 'compact';
    c.innerHTML = recs.map(b => {
        const g = getGrade(b.confidence||0), gc = getGradeClass(g);
        const typeLabel = b.bet_type === 'Moneyline' ? 'Winner' : b.bet_type === 'Total' ? 'Total Runs' : b.bet_type;
        const pickLabel = b.pick.replace(/ ML$/i,'');

        if (compact) return `<div class="bet-card-compact" onclick="toggleBetCard(this)">
            <div class="compact-left">
                <span class="grade ${gc}">${g}</span>
                <span class="bet-pick">${pickLabel}</span>
                <span class="compact-game">${b.game}</span>
            </div>
            <div class="compact-stats">
                ${compactStat('Confidence',pct(b.confidence||0,0),'edge-val')}
                ${compactStat('Win Prob',pct(b.true_prob),'roi-val')}
                ${compactStat('Type',typeLabel)}
            </div>
        </div>`;

        return `<div class="bet-card expanded">
            <div class="bet-header" onclick="toggleBetCard(this.parentElement)">
                <div><span class="grade ${gc}">${g}</span><span class="bet-pick">${pickLabel}</span></div>
                <span style="font-size:.78rem;color:var(--text-muted);font-weight:500">${b.game}</span>
            </div>
            <div class="bet-body">
                <div class="bet-key-metrics">
                    ${predMetric('Confidence',pct(b.confidence||0,0),'edge-val')}
                    ${predMetric('Win Prob',pct(b.true_prob),'roi-val')}
                    ${predMetric('Type',typeLabel)}
                </div>
                <div class="bet-details-inline">
                    ${detailInline('Implied Prob',pct(b.implied_prob||0))}
                    ${b.bet_type==='Total'?detailInline('Expected Total',(b.expected_total||'-')):''}
                </div>
            </div>
        </div>`;
    }).join('');
}

function toggleBetCard(el) { el.classList.toggle('expanded'); }

function toggleView() {
    const b = $('view-toggle'), next = b.dataset.view === 'full' ? 'compact' : 'full';
    b.dataset.view = next; b.textContent = next === 'compact' ? 'Full View' : 'Compact View';
    applyFilters();
}

// Game analysis
function displayGames(games) {
    $('games-list').innerHTML = games.map((g,i) => {
        const mp=g.model_probs, mk=g.market_probs, bp=g.blended_probs||mp, ci=g.context_indicators||{};
        const teamLine = (lbl,probs) => `<div class="game-stat"><div class="game-stat-label">${lbl}</div><div class="game-stat-value">${g.home}: ${pct(probs.home_win_prob)}<br>${g.away}: ${pct(probs.away_win_prob)}</div></div>`;
        return `<div class="game-card" onclick="toggleGameDetails(${i})">
            <div class="game-header">${g.game}</div>
            ${renderContextIndicators(ci)}
            <div class="game-stats">
                ${teamLine('Model Prediction',mp)}
                ${mk ? teamLine('Market Odds',mk)+teamLine('Blended',bp) : ''}
                <div class="game-stat"><div class="game-stat-label">Expected Total</div><div class="game-stat-value">${mp.expected_total?mp.expected_total.toFixed(1):'-'} runs${mp.total_line?`<br><span style="font-size:.78rem;color:var(--text-muted)">Line: ${mp.total_line}</span>`:''}</div></div>
                <div class="game-stat"><div class="game-stat-label">Model Confidence</div><div class="game-stat-value">${pct(mp.confidence||0,0)}<div class="confidence-bar"><div class="confidence-fill" style="width:${(mp.confidence||0)*100}%"></div></div></div></div>
                <div class="game-stat"><div class="game-stat-label">Similar Games</div><div class="game-stat-value">${g.n_similar||mp.n_games||'-'} games</div></div>
            </div>
            <div class="game-details-expanded" id="game-details-${i}">${renderGameDetails(g)}</div>
        </div>`;
    }).join('');
}

function renderContextIndicators(ci) {
    if (!ci||!Object.keys(ci).length) return '';
    const b=[];
    (ci.fatigue||[]).forEach(i => { b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${i.type==='B2B'?'😴':'💪'}</span>${i.team} ${i.type==='B2B'?'B2B':'Rested'}</span>`); });
    (ci.pitcher||[]).forEach(i => { const icon=i.type==='ace'?'🔥':'⚠️'; b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${icon}</span>${i.team} ${i.type==='ace'?'Ace':'Weak SP'} (${i.value.toFixed(0)})</span>`); });
    (ci.park||[]).forEach(i => { const icon=i.type==='hitter-friendly'?'🏟️':'⚾'; b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${icon}</span>${i.type} (${i.value})</span>`); });
    (ci.splits||[]).forEach(i => { const t={strong_home:'Strong Home',weak_home:'Weak Home',strong_road:'Strong Road',weak_road:'Weak Road'}[i.type]; b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${i.severity==='positive'?'🏠':'🛣️'}</span>${i.team} ${t}</span>`); });
    return b.length?`<div class="context-indicators">${b.join('')}</div>`:'';
}

function renderGameDetails(g) {
    let h='';
    const pm=g.pitcher_matchup;
    if (pm?.home&&pm?.away) {
        const pc = (t,label) => `<div class="goalie-card"><div class="goalie-name">${label}: ${t.name} (${t.handedness}HP)</div><div class="goalie-stats">
            <div class="goalie-stat-row"><span class="goalie-stat-label">ERA</span><span class="goalie-stat-value">${t.era.toFixed(2)}</span></div>
            <div class="goalie-stat-row"><span class="goalie-stat-label">WHIP</span><span class="goalie-stat-value">${t.whip.toFixed(2)}</span></div>
            <div class="goalie-stat-row"><span class="goalie-stat-label">K/9</span><span class="goalie-stat-value">${t.k_per_9.toFixed(1)}</span></div>
            <div class="goalie-stat-row"><span class="goalie-stat-label">FIP</span><span class="goalie-stat-value">${t.fip.toFixed(2)}</span></div>
        </div><div class="quality-score">${t.quality_score.toFixed(0)}</div></div>`;
        h+=`<div class="details-section"><h3>Pitcher Matchup</h3><div class="goalie-comparison">${pc(pm.home,g.home)}${pc(pm.away,g.away)}</div></div>`;
    }
    const sp=g.team_splits;
    if (sp?.home&&sp?.away) {
        const sc = (lbl,d) => `<div class="split-card"><div class="split-title">${lbl}</div><div class="split-stats">
            <div class="split-stat-row"><span class="split-stat-label">Win %</span><span class="split-stat-value">${pct(d.win_pct||0)}</span></div>
            <div class="split-stat-row"><span class="split-stat-label">RS/G</span><span class="split-stat-value">${(d.rs_pg||0).toFixed(2)}</span></div>
            <div class="split-stat-row"><span class="split-stat-label">RA/G</span><span class="split-stat-value">${(d.ra_pg||0).toFixed(2)}</span></div>
        </div></div>`;
        h+=`<div class="details-section"><h3>Home/Road Splits (Last 10)</h3><div class="splits-comparison">${sc(g.home+' at Home',sp.home)}${sc(g.away+' on Road',sp.away)}</div></div>`;
    }
    if (g.bullpen?.home&&g.bullpen?.away) {
        h+=`<div class="details-section"><h3>Bullpen Quality</h3><div class="advanced-stats-grid">
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.home} BP ERA</div><div class="advanced-stat-value">${(g.bullpen.home.bullpen_era||4).toFixed(2)}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.away} BP ERA</div><div class="advanced-stat-value">${(g.bullpen.away.bullpen_era||4).toFixed(2)}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.home} BP Quality</div><div class="advanced-stat-value">${(g.bullpen.home.bullpen_quality||50).toFixed(0)}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.away} BP Quality</div><div class="advanced-stat-value">${(g.bullpen.away.bullpen_quality||50).toFixed(0)}</div></div>
        </div></div>`;
    }
    if (g.park_factor) {
        h+=`<div class="details-section"><h3>Park Factor</h3><div class="advanced-stats-grid">
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.home} Park</div><div class="advanced-stat-value">${g.park_factor}</div></div>
        </div></div>`;
    }
    return h;
}

function toggleGameDetails(i) { $$('.game-card')[i].classList.toggle('expanded'); }

// Scroll-to-top
(function(){
    const b=document.createElement('button'); b.className='scroll-top-btn'; b.innerHTML='↑'; b.setAttribute('aria-label','Scroll to top');
    b.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));
    document.body.appendChild(b);
    window.addEventListener('scroll',()=>b.classList.toggle('visible',window.scrollY>400),{passive:true});
})();

let resizeT;
window.addEventListener('resize',()=>{clearTimeout(resizeT);resizeT=setTimeout(()=>{},250);});

loadAnalysis();
setInterval(loadAnalysis,3e5);
