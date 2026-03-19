// Global state
let allRecommendations = [];
let currentStake = 0.5;
let filtersSetUp = false;
let currentFilters = { grade: 'all', type: 'all', book: 'all', sortBy: 'edge' };

function showTab(tabName) {
    document.getElementById('today-tab').style.display = 'none';
    document.getElementById('performance-tab').style.display = 'none';
    document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));

    if (tabName === 'today') {
        document.getElementById('today-tab').style.display = 'block';
        document.querySelectorAll('.tab-button')[0].classList.add('active');
    } else {
        document.getElementById('performance-tab').style.display = 'block';
        document.querySelectorAll('.tab-button')[1].classList.add('active');
        loadPerformanceData();
    }
}

async function loadAnalysis() {
    try {
        const response = await fetch(`latest_analysis.json?v=${Date.now()}`);
        if (!response.ok) throw new Error(`Failed: ${response.status}`);
        const data = await response.json();
        displayAnalysis(data);
        document.getElementById('loading').style.display = 'none';
        showTab('today');
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('loading').style.display = 'none';
        document.getElementById('error').style.display = 'block';
    }
}

async function loadPerformanceData() {
    try {
        const ts = Date.now();
        const [rRes, hRes] = await Promise.all([
            fetch(`bet_results.json?v=${ts}`),
            fetch(`analysis_history.json?v=${ts}`)
        ]);
        let results = rRes.ok ? await rRes.json() : null;
        let history = hRes.ok ? await hRes.json() : null;
        displayPerformance(results, history);
    } catch (error) {
        displayNoPerformanceData();
    }
}

function displayPerformance(results, history) {
    if (!results || !results.results || Object.keys(results.results).length === 0) {
        displayNoPerformanceData();
        return;
    }

    const resolved = Object.values(results.results).filter(r => r.result !== 'push');
    const won = resolved.filter(r => r.result === 'won');
    const totalStaked = resolved.reduce((s, r) => s + r.bet.stake, 0);
    const totalProfit = resolved.reduce((s, r) => s + r.profit, 0);

    document.getElementById('perf-total-bets').textContent = resolved.length;
    document.getElementById('perf-win-rate').textContent = `${(won.length / resolved.length * 100).toFixed(1)}%`;
    document.getElementById('perf-roi').textContent = `${(totalProfit / totalStaked * 100).toFixed(1)}%`;
    document.getElementById('perf-profit').textContent = `$${totalProfit.toFixed(2)}`;

    const expectedGain = resolved.reduce((s, r) => s + (r.bet.stake * r.bet.edge), 0);
    document.getElementById('expected-gain').textContent = `$${expectedGain.toFixed(2)}`;
    document.getElementById('actual-gain').textContent = `$${totalProfit.toFixed(2)}`;
    const diff = totalProfit - expectedGain;
    const diffEl = document.getElementById('gain-difference');
    diffEl.textContent = `${diff >= 0 ? '+' : ''}$${diff.toFixed(2)}`;
    diffEl.className = `big-number ${diff >= 0 ? 'positive' : 'negative'}`;

    displayGradePerformance(resolved);
    displayRecentResults(resolved);
    displayProfitChart(resolved);
}

function displayGradePerformance(resolved) {
    const grades = {};
    resolved.forEach(r => {
        const grade = getGrade(r.bet.edge);
        if (!grades[grade]) grades[grade] = { bets: [], won: 0, staked: 0, profit: 0 };
        grades[grade].bets.push(r);
        grades[grade].staked += r.bet.stake;
        grades[grade].profit += r.profit;
        if (r.result === 'won') grades[grade].won++;
    });

    document.getElementById('grade-performance-list').innerHTML =
        ['A', 'B+', 'B', 'C+'].filter(g => grades[g]).map(grade => {
            const d = grades[grade];
            return `<div class="grade-performance-item">
                <div class="grade-performance-badge ${getGradeClass(grade)}">${grade}</div>
                <div class="grade-performance-stats">
                    <div class="grade-stat"><span class="grade-stat-label">Bets</span><span class="grade-stat-value">${d.bets.length}</span></div>
                    <div class="grade-stat"><span class="grade-stat-label">Win Rate</span><span class="grade-stat-value">${(d.won / d.bets.length * 100).toFixed(1)}%</span></div>
                    <div class="grade-stat"><span class="grade-stat-label">ROI</span><span class="grade-stat-value ${d.profit >= 0 ? 'positive' : 'negative'}">${(d.profit / d.staked * 100).toFixed(1)}%</span></div>
                    <div class="grade-stat"><span class="grade-stat-label">Profit</span><span class="grade-stat-value ${d.profit >= 0 ? 'positive' : 'negative'}">$${d.profit.toFixed(2)}</span></div>
                </div>
            </div>`;
        }).join('');
}

function displayRecentResults(resolved) {
    const sorted = [...resolved].sort((a, b) =>
        new Date(b.bet.analysis_timestamp || b.checked_at || 0) -
        new Date(a.bet.analysis_timestamp || a.checked_at || 0));
    document.getElementById('recent-results-list').innerHTML = sorted.slice(0, 20).map(r => {
        const grade = getGrade(r.bet.edge);
        const icon = r.result === 'won' ? '\u2705' : r.result === 'push' ? '\u2796' : '\u274C';
        const d = new Date(r.bet.analysis_timestamp || r.checked_at);
        return `<div class="result-item">
            <div class="result-icon">${icon}</div>
            <div class="result-details">
                <div class="result-pick">${r.bet.pick}</div>
                <div class="result-game">${r.bet.game}</div>
            </div>
            <div class="result-date">${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</div>
            <div class="result-grade ${getGradeClass(grade)}">${grade}</div>
            <div class="result-profit ${r.profit >= 0 ? 'positive' : 'negative'}">${r.profit >= 0 ? '+' : ''}$${r.profit.toFixed(2)}</div>
        </div>`;
    }).join('');
}

let profitChartInstance = null;
let allSortedBets = [];

function displayProfitChart(resolved) {
    allSortedBets = [...resolved].sort((a, b) =>
        new Date(a.bet.analysis_timestamp || a.checked_at || 0) -
        new Date(b.bet.analysis_timestamp || b.checked_at || 0));
    renderProfitChart(allSortedBets);
}

function setChartRange(range) {
    document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.range-btn[data-range="${range}"]`).classList.add('active');
    if (range === 'all') { renderProfitChart(allSortedBets); return; }
    const now = new Date();
    const cutoff = range === 'week'
        ? new Date(now - 7*864e5)
        : new Date(now - 30*864e5);
    renderProfitChart(allSortedBets.filter(r =>
        new Date(r.bet.analysis_timestamp || r.checked_at || 0) >= cutoff));
}

function renderProfitChart(bets) {
    const canvas = document.getElementById('profit-chart');
    if (!canvas || typeof Chart === 'undefined') return;
    if (profitChartInstance) profitChartInstance.destroy();
    if (!bets.length) return;

    let cum = 0, cumExp = 0;
    const labels = [], data = [], expData = [], colors = [];
    bets.forEach(r => {
        cum += r.profit;
        cumExp += r.bet.stake * r.bet.edge;
        labels.push(new Date(r.bet.analysis_timestamp || r.checked_at)
            .toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
        data.push(+cum.toFixed(2));
        expData.push(+cumExp.toFixed(2));
        colors.push(r.result === 'won' ? '#22C55E' : '#EF4444');
    });

    profitChartInstance = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'Actual Profit', data, borderColor: '#C41E3A', backgroundColor: 'rgba(196,30,58,0.1)', fill: true, tension: 0.3, borderWidth: 2.5, pointRadius: 4, pointBackgroundColor: colors, pointBorderColor: colors },
                { label: 'Expected (EV)', data: expData, borderColor: '#F4901E', borderDash: [6,3], borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3 }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { labels: { color: '#B8C4D0', font: { size: 12 }, usePointStyle: true, padding: 16 } },
                tooltip: { backgroundColor: 'rgba(20,25,35,0.95)', titleColor: '#E8EDF2', bodyColor: '#B8C4D0' }
            },
            scales: {
                x: { ticks: { color: '#6B7A8D', font: { size: 10 }, maxRotation: 45 }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y: { ticks: { color: '#6B7A8D', callback: v => `$${v.toFixed(2)}` }, grid: { color: 'rgba(255,255,255,0.05)' }, title: { display: true, text: 'Cumulative Profit ($)', color: '#6B7A8D' } }
            }
        }
    });
}

function displayNoPerformanceData() {
    ['grade-performance-list', 'recent-results-list'].forEach(id => {
        document.getElementById(id).innerHTML = `<div class="no-data"><p>No performance data yet.</p></div>`;
    });
    ['perf-total-bets', 'perf-win-rate', 'perf-roi', 'perf-profit'].forEach(id =>
        document.getElementById(id).textContent = id === 'perf-total-bets' ? '0' : '-');
}

function displayAnalysis(data) {
    const ts = new Date(data.timestamp);
    document.getElementById('timestamp').textContent = ts.toLocaleString('en-US', {
        month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York'
    }) + ' EST';
    document.getElementById('games-analyzed').textContent = data.games_analyzed.length;
    document.getElementById('bets-found').textContent = data.recommendations.length;

    if (data.recommendations.length > 0) {
        const totalStake = data.recommendations.length * data.stake;
        const totalEV = data.recommendations.reduce((s, b) => s + b.ev, 0);
        document.getElementById('expected-roi').textContent = `${(totalEV / totalStake * 100).toFixed(1)}%`;
    } else {
        document.getElementById('expected-roi').textContent = 'N/A';
    }

    allRecommendations = data.recommendations;
    currentStake = data.stake || 0.5;
    populateBookFilter(allRecommendations);
    setupFilters();
    displayRecommendations(allRecommendations, currentStake);
    displayGames(data.games_analyzed);
}

function setupFilters() {
    if (filtersSetUp) return;
    filtersSetUp = true;
    ['filter-grade', 'filter-type', 'filter-book', 'sort-by'].forEach(id => {
        document.getElementById(id).addEventListener('change', e => {
            const key = id === 'sort-by' ? 'sortBy' : id.replace('filter-', '');
            currentFilters[key] = e.target.value;
            applyFilters();
        });
    });
}

function applyFilters() {
    let filtered = [...allRecommendations];
    if (currentFilters.grade !== 'all') filtered = filtered.filter(b => getGrade(b.edge) === currentFilters.grade);
    if (currentFilters.type !== 'all') filtered = filtered.filter(b => b.bet_type === currentFilters.type);
    if (currentFilters.book !== 'all') filtered = filtered.filter(b => b.book === currentFilters.book);
    const sortFns = {
        edge: (a, b) => b.edge - a.edge,
        roi: (a, b) => b.roi - a.roi,
        confidence: (a, b) => b.confidence - a.confidence,
        book: (a, b) => a.book.localeCompare(b.book),
    };
    filtered.sort(sortFns[currentFilters.sortBy] || sortFns.edge);
    displayRecommendations(filtered, currentStake);
}

function populateBookFilter(recs) {
    const sel = document.getElementById('filter-book');
    const books = [...new Set(recs.map(b => b.book))].sort();
    sel.innerHTML = '<option value="all">All Books</option>';
    books.forEach(b => { const o = document.createElement('option'); o.value = b; o.textContent = formatBookName(b); sel.appendChild(o); });
}

function formatBookName(book) {
    const names = {
        fanduel: 'FanDuel', draftkings: 'DraftKings', betmgm: 'BetMGM', pointsbet: 'PointsBet',
        bet365: 'Bet365', pinnacle: 'Pinnacle', betrivers: 'BetRivers', bovada: 'Bovada',
        espnbet: 'ESPN Bet', fanatics: 'Fanatics', hardrockbet: 'Hard Rock Bet', ballybet: 'Bally Bet',
        wynnbet: 'WynnBet', superbook: 'SuperBook', lowvig: 'LowVig', betonlineag: 'BetOnline',
    };
    return names[book.toLowerCase()] || book.charAt(0).toUpperCase() + book.slice(1);
}

function displayRecommendations(recs, stake) {
    const container = document.getElementById('recommendations-list');
    if (!recs.length) { container.innerHTML = '<div class="no-data"><p>No +EV bets match your criteria.</p></div>'; return; }

    const isCompact = document.getElementById('view-toggle')?.dataset.view === 'compact';
    container.innerHTML = recs.map(bet => {
        const grade = getGrade(bet.edge);
        const gc = getGradeClass(grade);
        const lineShop = isCompact ? '' : renderLineShopping(bet);

        if (isCompact) {
            return `<div class="bet-card-compact">
                <div class="compact-left"><span class="grade ${gc}">${grade}</span><span class="bet-pick">${bet.pick}</span><span class="compact-game">${bet.game}</span></div>
                <div class="compact-stats">
                    <div class="compact-stat"><span class="compact-stat-label">Edge</span><span class="compact-stat-value edge-val">${(bet.edge*100).toFixed(1)}%</span></div>
                    <div class="compact-stat"><span class="compact-stat-label">ROI</span><span class="compact-stat-value roi-val">${(bet.roi*100).toFixed(1)}%</span></div>
                    <div class="compact-stat"><span class="compact-stat-label">Odds</span><span class="compact-stat-value odds-val">${bet.odds>0?'+':''}${bet.odds}</span></div>
                    <div class="compact-stat"><span class="compact-stat-label">Book</span><span class="compact-stat-value">${formatBookName(bet.book)}</span></div>
                    <div class="compact-stat"><span class="compact-stat-label">Model</span><span class="compact-stat-value">${(bet.true_prob*100).toFixed(1)}%</span></div>
                    <div class="compact-stat"><span class="compact-stat-label">Conf</span><span class="compact-stat-value">${(bet.confidence*100).toFixed(0)}%</span></div>
                </div>
            </div>`;
        }

        return `<div class="bet-card">
            <div class="bet-header"><div><span class="grade ${gc}">${grade}</span><span class="bet-pick">${bet.pick}</span></div><span style="font-size:0.78rem;color:var(--text-muted);font-weight:500;">${bet.game}</span></div>
            <div class="bet-key-metrics">
                <div class="key-metric"><div class="key-metric-label">Edge</div><div class="key-metric-value edge-val">${(bet.edge*100).toFixed(1)}%</div></div>
                <div class="key-metric"><div class="key-metric-label">ROI</div><div class="key-metric-value roi-val">${(bet.roi*100).toFixed(1)}%</div></div>
                <div class="key-metric"><div class="key-metric-label">EV / $${stake.toFixed(2)}</div><div class="key-metric-value ev-val">$${(bet.stake*bet.roi).toFixed(2)}</div></div>
                <div class="key-metric"><div class="key-metric-label">Best Odds</div><div class="key-metric-value odds-val">${bet.odds>0?'+':''}${bet.odds}</div></div>
            </div>
            <div class="bet-details-inline">
                <div class="detail-item-inline"><span class="detail-label">Type</span><span class="detail-value">${bet.bet_type}</span></div>
                <div class="detail-item-inline"><span class="detail-label">Best Book</span><span class="detail-value">${formatBookName(bet.book)}</span></div>
                <div class="detail-item-inline"><span class="detail-label">Model Prob</span><span class="detail-value">${(bet.true_prob*100).toFixed(1)}%</span></div>
                <div class="detail-item-inline"><span class="detail-label">Implied Prob</span><span class="detail-value">${(bet.implied_prob*100).toFixed(1)}%</span></div>
                <div class="detail-item-inline"><span class="detail-label">Confidence</span><span class="detail-value">${(bet.confidence*100).toFixed(0)}%</span></div>
            </div>
            ${lineShop}
        </div>`;
    }).join('');
}

function renderLineShopping(bet) {
    const list = bet.all_book_odds || [];
    if (list.length <= 1) return '';
    const best = list[0].odds;
    return `<div class="line-shopping">
        <div class="line-shopping-header"><span class="line-shopping-title">Line Shopping</span></div>
        <div class="line-shopping-grid">
            ${list.map(item => {
                const isBest = item.odds === best;
                const odds = typeof item.odds === 'number' ? `${item.odds>0?'+':''}${item.odds}` : item.odds;
                const pt = item.point !== undefined ? ` (${item.point})` : '';
                return `<div class="line-shop-item ${isBest?'best-odds':''}">
                    <span class="line-shop-book">${formatBookName(item.book)}</span>
                    <span><span class="line-shop-odds">${odds}${pt}</span>${isBest?'<span class="line-shop-best-tag">Best</span>':''}</span>
                </div>`;
            }).join('')}
        </div>
    </div>`;
}

function displayGames(games) {
    document.getElementById('games-list').innerHTML = games.map((game, i) => {
        const mp = game.model_probs;
        const mk = game.market_probs || null;
        const bp = game.blended_probs || mp;
        const ctx = game.context_indicators || {};

        return `<div class="game-card" onclick="this.classList.toggle('expanded')">
            <div class="game-header">
                ${game.game}
                ${(game.n_bets||0) > 0 ? `<span style="color:var(--accent-bright);font-size:0.82rem;font-weight:600;"> &middot; ${game.n_bets} +EV bet${game.n_bets>1?'s':''}</span>` : ''}
            </div>
            ${renderContextBadges(ctx)}
            <div class="game-stats">
                <div class="game-stat"><div class="game-stat-label">Model Prediction</div><div class="game-stat-value">${game.home}: ${(mp.home_win_prob*100).toFixed(1)}%<br>${game.away}: ${(mp.away_win_prob*100).toFixed(1)}%</div></div>
                ${mk ? `<div class="game-stat"><div class="game-stat-label">Market Odds</div><div class="game-stat-value">${game.home}: ${(mk.home_win_prob*100).toFixed(1)}%<br>${game.away}: ${(mk.away_win_prob*100).toFixed(1)}%</div></div>
                <div class="game-stat"><div class="game-stat-label">Blended</div><div class="game-stat-value">${game.home}: ${(bp.home_win_prob*100).toFixed(1)}%<br>${game.away}: ${(bp.away_win_prob*100).toFixed(1)}%</div></div>` : ''}
                <div class="game-stat"><div class="game-stat-label">Expected Total</div><div class="game-stat-value">${mp.expected_total ? mp.expected_total.toFixed(1) : '-'} runs${mp.total_line ? `<br><span style="font-size:0.78rem;color:var(--text-muted);">Line: ${mp.total_line}</span>` : ''}</div></div>
                <div class="game-stat"><div class="game-stat-label">Confidence</div><div class="game-stat-value">${((mp.confidence||0)*100).toFixed(0)}%<div class="confidence-bar"><div class="confidence-fill" style="width:${(mp.confidence||0)*100}%"></div></div></div></div>
                <div class="game-stat"><div class="game-stat-label">Similar Games</div><div class="game-stat-value">${game.n_similar||mp.n_games||'-'} games</div></div>
            </div>
            <div class="game-details-expanded">${renderGameDetails(game)}</div>
        </div>`;
    }).join('');
}

function renderContextBadges(ctx) {
    let badges = [];
    if (ctx.fatigue) ctx.fatigue.forEach(i => {
        const icon = i.type === 'B2B' ? '\uD83D\uDE34' : '\uD83D\uDCAA';
        badges.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${icon}</span>${i.team} ${i.type === 'B2B' ? 'B2B' : 'Rested'}</span>`);
    });
    if (ctx.pitcher) ctx.pitcher.forEach(i => {
        const icon = i.type === 'ace' ? '\uD83D\uDD25' : '\u26A0\uFE0F';
        badges.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${icon}</span>${i.team} ${i.type === 'ace' ? 'Ace' : 'Weak SP'} (${i.value.toFixed(0)})</span>`);
    });
    if (ctx.park) ctx.park.forEach(i => {
        const icon = i.type === 'hitter-friendly' ? '\uD83C\uDFDF\uFE0F' : '\u26BE';
        badges.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${icon}</span>${i.type} (${i.value})</span>`);
    });
    return badges.length ? `<div class="context-indicators">${badges.join('')}</div>` : '';
}

function renderGameDetails(game) {
    let html = '';
    // Pitcher matchup
    if (game.pitcher_matchup && game.pitcher_matchup.home && game.pitcher_matchup.away) {
        const hp = game.pitcher_matchup.home, ap = game.pitcher_matchup.away;
        html += `<div class="details-section"><h3>Pitcher Matchup</h3>
            <div class="goalie-comparison">
                <div class="goalie-card">
                    <div class="goalie-name">${game.home}: ${hp.name} (${hp.handedness}HP)</div>
                    <div class="goalie-stats">
                        <div class="goalie-stat-row"><span class="goalie-stat-label">ERA</span><span class="goalie-stat-value">${hp.era.toFixed(2)}</span></div>
                        <div class="goalie-stat-row"><span class="goalie-stat-label">WHIP</span><span class="goalie-stat-value">${hp.whip.toFixed(2)}</span></div>
                        <div class="goalie-stat-row"><span class="goalie-stat-label">K/9</span><span class="goalie-stat-value">${hp.k_per_9.toFixed(1)}</span></div>
                        <div class="goalie-stat-row"><span class="goalie-stat-label">FIP</span><span class="goalie-stat-value">${hp.fip.toFixed(2)}</span></div>
                    </div>
                    <div class="quality-score">${hp.quality_score.toFixed(0)}</div>
                </div>
                <div class="goalie-card">
                    <div class="goalie-name">${game.away}: ${ap.name} (${ap.handedness}HP)</div>
                    <div class="goalie-stats">
                        <div class="goalie-stat-row"><span class="goalie-stat-label">ERA</span><span class="goalie-stat-value">${ap.era.toFixed(2)}</span></div>
                        <div class="goalie-stat-row"><span class="goalie-stat-label">WHIP</span><span class="goalie-stat-value">${ap.whip.toFixed(2)}</span></div>
                        <div class="goalie-stat-row"><span class="goalie-stat-label">K/9</span><span class="goalie-stat-value">${ap.k_per_9.toFixed(1)}</span></div>
                        <div class="goalie-stat-row"><span class="goalie-stat-label">FIP</span><span class="goalie-stat-value">${ap.fip.toFixed(2)}</span></div>
                    </div>
                    <div class="quality-score">${ap.quality_score.toFixed(0)}</div>
                </div>
            </div>
        </div>`;
    }

    // Home/Road splits
    if (game.team_splits && game.team_splits.home && game.team_splits.away) {
        const hs = game.team_splits.home, as = game.team_splits.away;
        html += `<div class="details-section"><h3>Home/Road Splits (Last 10)</h3>
            <div class="splits-comparison">
                <div class="split-card">
                    <div class="split-title">${game.home} at Home</div>
                    <div class="split-stats">
                        <div class="split-stat-row"><span class="split-stat-label">Win %</span><span class="split-stat-value">${((hs.win_pct||0)*100).toFixed(1)}%</span></div>
                        <div class="split-stat-row"><span class="split-stat-label">RS/G</span><span class="split-stat-value">${(hs.rs_pg||0).toFixed(2)}</span></div>
                        <div class="split-stat-row"><span class="split-stat-label">RA/G</span><span class="split-stat-value">${(hs.ra_pg||0).toFixed(2)}</span></div>
                    </div>
                </div>
                <div class="split-card">
                    <div class="split-title">${game.away} on Road</div>
                    <div class="split-stats">
                        <div class="split-stat-row"><span class="split-stat-label">Win %</span><span class="split-stat-value">${((as.win_pct||0)*100).toFixed(1)}%</span></div>
                        <div class="split-stat-row"><span class="split-stat-label">RS/G</span><span class="split-stat-value">${(as.rs_pg||0).toFixed(2)}</span></div>
                        <div class="split-stat-row"><span class="split-stat-label">RA/G</span><span class="split-stat-value">${(as.ra_pg||0).toFixed(2)}</span></div>
                    </div>
                </div>
            </div>
        </div>`;
    }

    // Bullpen
    if (game.bullpen && game.bullpen.home && game.bullpen.away) {
        html += `<div class="details-section"><h3>Bullpen Quality</h3>
            <div class="advanced-stats-grid">
                <div class="advanced-stat-card"><div class="advanced-stat-label">${game.home} BP ERA</div><div class="advanced-stat-value">${(game.bullpen.home.bullpen_era||4).toFixed(2)}</div></div>
                <div class="advanced-stat-card"><div class="advanced-stat-label">${game.away} BP ERA</div><div class="advanced-stat-value">${(game.bullpen.away.bullpen_era||4).toFixed(2)}</div></div>
                <div class="advanced-stat-card"><div class="advanced-stat-label">${game.home} BP Quality</div><div class="advanced-stat-value">${(game.bullpen.home.bullpen_quality||50).toFixed(0)}</div></div>
                <div class="advanced-stat-card"><div class="advanced-stat-label">${game.away} BP Quality</div><div class="advanced-stat-value">${(game.bullpen.away.bullpen_quality||50).toFixed(0)}</div></div>
            </div>
        </div>`;
    }

    // Park factor
    if (game.park_factor) {
        html += `<div class="details-section"><h3>Park Factor</h3>
            <div class="advanced-stats-grid">
                <div class="advanced-stat-card"><div class="advanced-stat-label">${game.home} Park</div><div class="advanced-stat-value">${game.park_factor}</div></div>
            </div>
        </div>`;
    }

    return html;
}

function getGrade(edge) {
    if (edge >= 0.07) return 'A';
    if (edge >= 0.04) return 'B+';
    if (edge >= 0.03) return 'B';
    return 'C+';
}

function getGradeClass(grade) {
    return { 'A': 'grade-a', 'B+': 'grade-b-plus', 'B': 'grade-b', 'C+': 'grade-c-plus' }[grade] || 'grade-c-plus';
}

function toggleView() {
    const btn = document.getElementById('view-toggle');
    const next = btn.dataset.view === 'full' ? 'compact' : 'full';
    btn.dataset.view = next;
    btn.textContent = next === 'compact' ? 'Full View' : 'Compact View';
    applyFilters();
}

loadAnalysis();
setInterval(loadAnalysis, 5 * 60 * 1000);
