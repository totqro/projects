let weekData = null, perfLoaded = false;

const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);
const pct = (v, d=1) => (v*100).toFixed(d) + '%';
const ET = {timeZone: 'America/New_York'};
const fmtKick = iso => new Date(iso).toLocaleString('en-US', {...ET, weekday:'short', hour:'numeric', minute:'2-digit'}) + ' ET';
const fmtDay = iso => new Date(iso).toLocaleDateString('en-US', {...ET, month:'short', day:'numeric'});

function getGrade(conf) { return conf>=.75?'A':conf>=.65?'B+':conf>=.55?'B':'C+'; }
function getGradeClass(g) { return {A:'grade-a','B+':'grade-b-plus',B:'grade-b','C+':'grade-c-plus'}[g]||'grade-c-plus'; }

function showTab(t) {
    ['week-tab','performance-tab'].forEach(id => { if ($(id)) $(id).style.display = 'none'; });
    $$('.tab-button').forEach(b => b.classList.remove('active'));
    const idx = t === 'performance' ? 1 : 0;
    $(idx ? 'performance-tab' : 'week-tab').style.display = 'block';
    $$('.tab-button')[idx].classList.add('active');
    if (idx) loadPerformance();
}

async function loadWeek() {
    try {
        const r = await fetch(`latest_analysis.json?v=${Date.now()}`);
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        weekData = await r.json();
        displayWeek();
        if ($('loading').style.display !== 'none') { $('loading').style.display = 'none'; showTab('week'); }
    } catch (e) {
        console.error(e);
        $('loading').style.display = 'none';
        const el = $('error'); el.style.display = 'block';
        el.innerHTML = `<p>Could not load prediction data. Make sure latest_analysis.json is available.</p>`;
    }
}

function displayWeek() {
    const d = weekData, games = d.games_analyzed || [];
    $('week-title').textContent = `${d.season} Week ${d.week}`;
    $('timestamp').textContent = new Date(d.timestamp).toLocaleString('en-US', {...ET, month:'short', day:'numeric', hour:'numeric', minute:'2-digit'}) + ' ET';
    $('games-count').textContent = games.length;
    $('logged-count').textContent = `${d.logged}/${games.length}`;
    const decided = games.filter(g => g.correct != null);
    $('week-record').textContent = decided.length ? `${decided.filter(g => g.correct).length}-${decided.filter(g => !g.correct).length}` : '-';
    renderWeek();
}

function renderWeek() {
    if (!weekData) return;
    let games = [...(weekData.games_analyzed || [])];
    const conf = g => g.home_win_prob != null ? Math.abs(g.home_win_prob - 0.5) : -1;
    if (($('sort-games')?.value || 'kickoff') === 'confidence') games.sort((a, b) => conf(b) - conf(a));
    else games.sort((a, b) => a.kickoff.localeCompare(b.kickoff));
    const el = $('games-list');
    el.innerHTML = games.length
        ? games.map((g, i) => renderGameCard(g, i)).join('')
        : `<div class="no-data"><div class="no-data-icon">🏈</div><p>No games this week.</p></div>`;
}

function statusLine(g) {
    switch (g.status) {
        case 'final': {
            const res = `Final · ${g.away} ${g.away_score} @ ${g.home} ${g.home_score}`;
            if (g.correct == null) return `<span class="gc-status">${res}${g.home_win_prob == null ? ' · not logged' : ''}</span>`;
            return `<span class="gc-status ${g.correct ? 'ok' : 'bad'}">${g.correct ? '✅' : '❌'} ${res}</span>`;
        }
        case 'in_progress': return `<span class="gc-status live">In progress · kicked off ${fmtKick(g.kickoff)}</span>`;
        case 'logged':      return `<span class="gc-status">Kickoff ${fmtKick(g.kickoff)} · logged ${fmtDay(g.logged_at)}</span>`;
        case 'missed':      return `<span class="gc-status bad">Kicked off without a logged prediction</span>`;
        default:            return `<span class="gc-status">Kickoff ${fmtKick(g.kickoff)} · posts after final injury report (${fmtKick(g.report_due)})</span>`;
    }
}

function renderGameCard(g, i) {
    const has = g.home_win_prob != null;
    const hp = has ? g.home_win_prob : 0.5, ap = 1 - hp;
    const homeFav = hp > ap;
    const conf = Math.max(hp, ap);
    const isStrong = has && conf >= 0.65;
    const grade = has ? getGrade(conf) : null;
    const homePct = (hp*100).toFixed(0), awayPct = (ap*100).toFixed(0);
    const final = g.status === 'final';
    const awayWon = final && g.away_score > g.home_score, homeWon = final && g.home_score > g.away_score;
    const row = (team, p, fav, score, won) => `<div class="gc-team-row${has && fav ? ' gc-winner' : ''}${final ? ' gc-final' : ''}">
            <span class="gc-tname">${team}</span>
            <div class="gc-bar-wrap"><div class="gc-bar" style="width:${has ? (p*100).toFixed(0) : 50}%"></div></div>
            <span class="gc-tpct">${has ? (p*100).toFixed(0) + '%' : '—'}</span>
            ${final ? `<span class="gc-score${won ? ' won' : ''}">${score}</span>` : ''}
        </div>`;
    const mkt = g.market_home_prob != null ? `<span class="gc-line">Market ${g.home} ${(g.market_home_prob*100).toFixed(0)}%</span>` : '';
    return `<div class="gc cy-panel${isStrong ? ' gc-strong' : ''}${has ? '' : ' gc-pending'}" id="gc-${i}">
        <div class="gc-header" onclick="toggleGC(${i})">
            <div class="gc-matchup">
                <span class="${has && !homeFav ? 'gc-pick-team' : ''}">${g.away}</span>
                <span class="gc-sep">@</span>
                <span class="${has && homeFav ? 'gc-pick-team' : ''}">${g.home}</span>
            </div>
            ${grade ? `<span class="grade ${getGradeClass(grade)} gc-grade">${grade}</span>` : ''}
        </div>
        <div class="gc-probs" onclick="toggleGC(${i})">
            ${row(g.away, ap, !homeFav, g.away_score, awayWon)}
            ${row(g.home, hp, homeFav, g.home_score, homeWon)}
        </div>
        <div class="gc-footer" onclick="toggleGC(${i})">
            <div class="gc-total">
                <span class="gc-total-num">${has ? g.expected_total.toFixed(1) : '—'}</span>
                <span class="gc-total-unit">exp. points</span>
                ${has ? `<span class="gc-line">${g.away} ${g.expected_away_points.toFixed(1)} · ${g.home} ${g.expected_home_points.toFixed(1)}</span>` : ''}
                ${mkt}
            </div>
            <div class="gc-conf">
                <span class="gc-conf-label">Pick</span>
                <div class="confidence-bar gc-conf-bar"><div class="confidence-fill" style="width:${has ? (conf*100).toFixed(0) : 0}%"></div></div>
                <span class="gc-conf-pct">${has ? (conf*100).toFixed(0) + '%' : '—'}</span>
            </div>
        </div>
        <div class="gc-context" onclick="toggleGC(${i})">${statusLine(g)}</div>
        <div class="gc-expanded" id="gced-${i}" style="display:none">${renderGameDetails(g)}</div>
    </div>`;
}

function toggleGC(i) {
    const el = $(`gced-${i}`), card = $(`gc-${i}`);
    const open = el.style.display !== 'none';
    el.style.display = open ? 'none' : 'block';
    card.classList.toggle('gc-open', !open);
}

function renderGameDetails(g) {
    if (g.home_win_prob == null) {
        return `<div class="details-section"><p class="parlay-subtitle">The model's number for this game is held until the final injury report is published (${fmtKick(g.report_due || g.kickoff)}). The model was trained on final reports, so a mid-week prediction would not be the same model.</p></div>`;
    }
    const fav = g.home_win_prob > 0.5 ? g.home : g.away;
    const margin = Math.abs(g.expected_margin).toFixed(1);
    const card = (label, val) => `<div class="advanced-stat-card"><div class="advanced-stat-label">${label}</div><div class="advanced-stat-value">${val}</div></div>`;
    let h = `<div class="details-section"><h3>Model vs Market</h3><div class="advanced-stats-grid">
        ${card(`Model ${g.home}`, pct(g.home_win_prob))}
        ${card(`Market ${g.home}`, g.market_home_prob != null ? pct(g.market_home_prob) : '-')}
        ${card('Expected margin', `${fav} by ${margin}`)}
        ${card('Expected total', g.expected_total.toFixed(1))}
    </div></div>`;
    if (g.status === 'final') {
        const m = g.home_score - g.away_score;
        h += `<div class="details-section"><h3>Result</h3><div class="advanced-stats-grid">
            ${card('Final', `${g.away} ${g.away_score} @ ${g.home} ${g.home_score}`)}
            ${card('Actual margin', m === 0 ? 'tie' : `${m > 0 ? g.home : g.away} by ${Math.abs(m)}`)}
            ${card('Actual total', g.home_score + g.away_score)}
            ${card('Logged', fmtDay(g.logged_at))}
        </div></div>`;
    }
    return h;
}

// ---- Performance ---------------------------------------------------------- //
async function loadPerformance() {
    if (perfLoaded) return;
    try {
        const r = await fetch(`performance.json?v=${Date.now()}`);
        if (!r.ok) { noPerformance(); return; }
        displayPerformance(await r.json());
        perfLoaded = true;
    } catch (e) { console.error(e); noPerformance(); }
}

function displayPerformance(d) {
    const s = d.season_summary || {};
    if (!s.n) { noPerformance(); renderTestSet(d.test_set); return; }
    $('perf-title').textContent = `${d.season} Season Accuracy`;
    $('perf-n').textContent = s.n;
    $('perf-acc').textContent = `${pct(s.model.accuracy)}`;
    $('perf-ll').textContent = s.market ? `${s.model.log_loss.toFixed(3)} (${s.market.log_loss.toFixed(3)})` : s.model.log_loss.toFixed(3);
    $('perf-total').textContent = s.total_mae != null ? s.total_mae.toFixed(1) : '-';

    const row = (label, m, strong, extra='') => m && m.n ? `<div class="pred-result-row bench-row${strong ? ' bench-row--model' : ''}">
            <span class="pred-result-matchup">${label}<span class="pred-result-date"> · ${m.n}</span></span>
            <span class="pred-result-winner">${m.correct != null && extra !== 'nocount' ? `${m.correct}/${m.n} · ${pct(m.accuracy)}` : ''}</span>
            <span class="pred-result-winner">LL ${m.log_loss.toFixed(4)}<span class="score"> · Brier ${m.brier.toFixed(4)}</span></span>
        </div>` : '';
    let h = row('This model', s.model, true) + row('Market close', s.market) + row('Coin flip', s.coin_flip, false, 'nocount');
    if (s.favourite_agreement != null) h += `<p class="parlay-subtitle" style="margin-top:12px">Same favourite as the market in ${pct(s.favourite_agreement, 0)} of games.`
        + ` Points: margin MAE ${s.margin_mae} (market spread ${s.market_margin_mae ?? '-'}), total MAE ${s.total_mae} (market total ${s.market_total_mae ?? '-'}).</p>`;
    if (s.n < d.min_games_for_verdict) h += `<p class="parlay-subtitle">${s.n} games is under ${d.min_games_for_verdict}: any model-vs-market gap here is noise, not evidence.</p>`;
    $('bench-table').innerHTML = h;

    $('weeks-table').innerHTML = (d.weeks || []).slice().reverse().map(w => `<div class="pred-result-row week-row">
            <span class="pred-result-date">Week ${w.week}</span>
            <span class="pred-result-matchup">${w.model.correct}-${w.n - w.model.correct}<span class="pred-result-date"> · mkt ${w.market ? `${w.market.correct}-${w.market.n - w.market.correct}` : '-'}</span></span>
            <span class="pred-result-winner">LL ${w.model.log_loss.toFixed(3)}</span>
            <span class="pred-result-winner"><span class="score">mkt ${w.market ? w.market.log_loss.toFixed(3) : '-'}</span></span>
        </div>`).join('');

    renderTestSet(d.test_set);

    $('recent-results-list').innerHTML = (d.results || []).map(r => {
        const icon = r.correct == null ? '➖' : r.correct ? '✅' : '❌';
        const mIcon = r.market_correct == null ? '' : r.market_correct ? '✅' : '❌';
        const aw = r.away_score > r.home_score, hw = r.home_score > r.away_score;
        const team = (t, s, won) => won ? `<b>${t} ${s}</b>` : `${t} ${s}`;
        return `<div class="pred-result-row">
            <span class="pred-result-date">Wk ${r.week}</span>
            <span class="pred-result-matchup">${team(r.away, r.away_score, aw)} @ ${team(r.home, r.home_score, hw)}</span>
            <span class="pred-result-winner">${icon} ${r.pick} ${(r.pick_prob*100).toFixed(0)}%</span>
            <span class="pred-result-total"><span class="actual">mkt ${r.market_pick ? `${mIcon} ${r.market_pick} ${(r.market_pick_prob*100).toFixed(0)}%` : '-'}</span></span>
        </div>`;
    }).join('');
}

function renderTestSet(t) {
    if (!t) return;
    $('test-table').innerHTML = t.rows.map(r => `<div class="pred-result-row bench-row${r.model ? ' bench-row--model' : ''}">
            <span class="pred-result-matchup">${r.name}<span class="pred-result-date"> · ${t.n}</span></span>
            <span class="pred-result-winner">${pct(r.accuracy)}</span>
            <span class="pred-result-winner">LL ${r.log_loss.toFixed(4)}<span class="score"> · Brier ${r.brier.toFixed(4)}</span></span>
        </div>`).join('');
}

function noPerformance() {
    $('recent-results-list').innerHTML = `<div class="no-data"><div class="no-data-icon">📊</div><p>No scored games yet this season.</p></div>`;
    ['perf-n','perf-acc','perf-ll','perf-total'].forEach(id => $(id).textContent = '-');
}

(function(){
    const b = document.createElement('button'); b.className = 'scroll-top-btn'; b.innerHTML = '↑'; b.setAttribute('aria-label', 'Scroll to top');
    b.addEventListener('click', () => window.scrollTo({top:0, behavior:'smooth'}));
    document.body.appendChild(b);
    window.addEventListener('scroll', () => b.classList.toggle('visible', window.scrollY > 400), {passive:true});
})();

loadWeek();
setInterval(loadWeek, 3e5);
