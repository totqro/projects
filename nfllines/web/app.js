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
    const mkt = g.market_home_prob != null ? `<span class="gc-line">Vegas: ${vegasFav(g)}</span>` : '';
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
                <span class="gc-total-unit">Projected</span>
                <span class="gc-total-num">${has ? `${g.away} ${Math.round(g.expected_away_points)} - ${g.home} ${Math.round(g.expected_home_points)}` : '—'}</span>
                ${mkt}
            </div>
            <div class="gc-conf">
                <span class="gc-conf-label">${has ? `Pick: ${homeFav ? g.home : g.away}` : 'Pick'}</span>
                <div class="confidence-bar gc-conf-bar"><div class="confidence-fill" style="width:${has ? (conf*100).toFixed(0) : 0}%"></div></div>
                <span class="gc-conf-pct">${has ? (conf*100).toFixed(0) + '%' : '—'}</span>
            </div>
        </div>
        <div class="gc-context" onclick="toggleGC(${i})">${statusLine(g)}</div>
        <div class="gc-expanded" id="gced-${i}" style="display:none">${renderGameDetails(g)}</div>
    </div>`;
}

// Vegas's favourite and its win chance, from the de-vigged moneyline.
function vegasFav(g) {
    const p = g.market_home_prob;
    if (p == null) return '-';
    return `${p >= 0.5 ? g.home : g.away} ${pct(Math.max(p, 1 - p), 0)}`;
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
    const card = (label, val) => `<div class="advanced-stat-card"><div class="advanced-stat-label">${label}</div><div class="advanced-stat-value">${val}</div></div>`;
    const modelFav = `${fav} ${pct(Math.max(g.home_win_prob, 1 - g.home_win_prob), 0)}`;
    let h = `<div class="details-section"><h3>Model vs Vegas</h3><div class="advanced-stats-grid">
        ${card('Model favours', modelFav)}
        ${card('Vegas favours', vegasFav(g))}
        ${card('Projected winning margin', `${fav} by ${Math.round(Math.abs(g.expected_margin))}`)}
        ${card('Projected total points', Math.round(g.expected_total))}
    </div></div>`;
    if (g.status === 'final') {
        const m = g.home_score - g.away_score;
        h += `<div class="details-section"><h3>Result</h3><div class="advanced-stats-grid">
            ${card('Final', `${g.away} ${g.away_score} @ ${g.home} ${g.home_score}`)}
            ${card('Actual winning margin', m === 0 ? 'tie' : `${m > 0 ? g.home : g.away} by ${Math.abs(m)}`)}
            ${card('Actual total points', g.home_score + g.away_score)}
            ${card('Prediction posted', fmtDay(g.logged_at))}
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

const rec = (w, n) => `${w}-${n - w}`;
const tbl = rows => rows.map(([a, b, c, strong]) => `<div class="pred-result-row bench-row${strong ? ' bench-row--model' : ''}">
        <span class="pred-result-matchup">${a}</span>
        <span class="pred-result-winner">${b}</span>
        <span class="pred-result-winner"><span class="score">${c}</span></span>
    </div>`).join('');

function displayPerformance(d) {
    const s = d.season_summary || {};
    if (!s.n) { noPerformance(); renderTestSet(d.test_set); return; }
    const results = d.results || [];
    const m = s.model, v = s.market;
    $('perf-title').textContent = `How It's Doing: ${d.season} Season`;
    $('perf-acc').textContent = `${m.correct} of ${m.n} (${pct(m.accuracy, 0)})`;
    $('perf-vegas').textContent = v ? `${v.correct} of ${v.n} (${pct(v.accuracy, 0)})` : '-';
    const conf = results.filter(r => r.correct != null && r.pick_prob >= 0.70);
    const confW = conf.filter(r => r.correct).length;
    $('perf-confident').textContent = conf.length ? `${confW} of ${conf.length}` : 'none yet';
    $('perf-miss').textContent = s.margin_mae != null ? `${s.margin_mae.toFixed(1)} pts` : '-';

    // One plain sentence on where things stand, honest about sample size.
    let verdict = '';
    if (v) {
        const diff = m.correct - v.correct;
        verdict = diff > 0 ? `So far the model has picked ${diff} more winner${diff > 1 ? 's' : ''} than Vegas. `
                : diff < 0 ? `So far Vegas has picked ${-diff} more winner${diff < -1 ? 's' : ''} than the model. `
                : 'So far the model and Vegas have picked the same number of winners. ';
    }
    if (s.n < d.min_games_for_verdict) verdict += `That is only ${s.n} games, so a couple of upsets either way can swing it. It takes about ${d.min_games_for_verdict} games (most of a season) before the comparison really means something.`;
    $('perf-verdict').textContent = verdict;

    // Confidence check, from every scored game.
    const buckets = [[0.5, 0.6, 'Toss-ups (50-59%)'], [0.6, 0.7, 'Leans (60-69%)'], [0.7, 0.8, 'Confident (70-79%)'], [0.8, 1.01, 'Strong (80%+)']];
    $('calibration-table').innerHTML = tbl(buckets.map(([lo, hi, label]) => {
        const b = results.filter(r => r.correct != null && r.pick_prob >= lo && r.pick_prob < hi);
        if (!b.length) return [label, 'no games yet', ''];
        const w = b.filter(r => r.correct).length;
        const said = b.reduce((t, r) => t + r.pick_prob, 0) / b.length;
        return [`${label}<span class="pred-result-date"> · ${b.length} game${b.length > 1 ? 's' : ''}</span>`,
                `favourite won ${w} of ${b.length} (${pct(w / b.length, 0)})`, `model said ${pct(said, 0)}`];
    })) + `<p class="parlay-subtitle" style="margin-top:10px">With only a handful of games per row, expect these to bounce around until late in the season.</p>`;

    // Model vs Vegas in plain terms.
    const dis = results.filter(r => r.market_pick && r.pick !== r.market_pick && r.correct != null);
    const disW = dis.filter(r => r.correct).length;
    let bench = [['Model', `record ${rec(m.correct, m.n)}`, `${pct(m.accuracy, 0)} right`, true]];
    if (v) bench.push(['Vegas', `record ${rec(v.correct, v.n)}`, `${pct(v.accuracy, 0)} right`]);
    bench.push(['Always pick the home team', `record ${rec(results.filter(r => r.correct != null && r.home_score > r.away_score).length, results.filter(r => r.correct != null).length)}`, 'the no-skill baseline']);
    let h = tbl(bench);
    const lines = [];
    if (s.favourite_agreement != null) lines.push(`The model and Vegas picked the same team in ${pct(s.favourite_agreement, 0)} of games.`);
    if (dis.length) lines.push(`When they disagreed (${dis.length} game${dis.length > 1 ? 's' : ''}), the model was right ${disW} time${disW === 1 ? '' : 's'} and Vegas ${dis.length - disW}.`);
    if (s.market_margin_mae != null) lines.push(`On the final score, the model's projected margin missed by ${s.margin_mae.toFixed(1)} points on average; the Vegas point spread missed by ${s.market_margin_mae.toFixed(1)}.`);
    if (s.market_total_mae != null) lines.push(`On total points, the model missed by ${s.total_mae.toFixed(1)} on average; the Vegas over/under missed by ${s.market_total_mae.toFixed(1)}.`);
    h += lines.map(l => `<p class="parlay-subtitle" style="margin-top:10px">${l}</p>`).join('');
    $('bench-table').innerHTML = h;

    $('weeks-table').innerHTML = tbl((d.weeks || []).slice().reverse().map(w => [
        `Week ${w.week}`, `model ${rec(w.model.correct, w.n)}`,
        w.market ? `Vegas ${rec(w.market.correct, w.market.n)}` : '']));

    renderTestSet(d.test_set);

    const nerd = (label, x, strong) => x && x.n ? [`${label}<span class="pred-result-date"> · ${x.n}</span>`, `log loss ${x.log_loss.toFixed(4)}`, `Brier ${x.brier.toFixed(4)}`, strong] : null;
    $('nerd-table').innerHTML = tbl([nerd('Model, this season', m, true), nerd('Vegas, this season', v), nerd('Coin flip', s.coin_flip)].filter(Boolean))
        + `<p class="parlay-subtitle" style="margin-top:10px">2024-2025 test: ${(d.test_set?.rows || []).map(r => `${r.name} ${r.log_loss.toFixed(4)} / ${r.brier.toFixed(4)}`).join(' · ')}.</p>`;

    $('recent-results-list').innerHTML = results.map(r => {
        const icon = r.correct == null ? '➖' : r.correct ? '✅' : '❌';
        const mIcon = r.market_correct == null ? '' : r.market_correct ? '✅' : '❌';
        const aw = r.away_score > r.home_score, hw = r.home_score > r.away_score;
        const team = (t, sc, won) => won ? `<b>${t} ${sc}</b>` : `${t} ${sc}`;
        return `<div class="pred-result-row">
            <span class="pred-result-date">Wk ${r.week}</span>
            <span class="pred-result-matchup">${team(r.away, r.away_score, aw)} @ ${team(r.home, r.home_score, hw)}</span>
            <span class="pred-result-winner">${icon} ${r.pick} ${(r.pick_prob*100).toFixed(0)}%</span>
            <span class="pred-result-total"><span class="actual">Vegas ${r.market_pick ? `${mIcon} ${r.market_pick} ${(r.market_pick_prob*100).toFixed(0)}%` : '-'}</span></span>
        </div>`;
    }).join('');
}

function renderTestSet(t) {
    if (!t) return;
    $('test-table').innerHTML = tbl(t.rows.map(r => [r.name, `picked the winner ${pct(r.accuracy, 1)}`, `${Math.round(r.accuracy * t.n)} of ${t.n}`, r.model]))
        + `<p class="parlay-subtitle" style="margin-top:10px">The model matched Vegas on picking winners, but Vegas was a bit better at judging how likely each result was, so the model is not a way to beat the betting market. It also beat the simple team rating system (Elo) it was built on top of, and did so in all nine earlier seasons it was checked on.</p>`;
}

function noPerformance() {
    $('recent-results-list').innerHTML = `<div class="no-data"><div class="no-data-icon">📊</div><p>No scored games yet this season.</p></div>`;
    ['perf-acc','perf-vegas','perf-confident','perf-miss'].forEach(id => $(id).textContent = '-');
}

(function(){
    const b = document.createElement('button'); b.className = 'scroll-top-btn'; b.innerHTML = '↑'; b.setAttribute('aria-label', 'Scroll to top');
    b.addEventListener('click', () => window.scrollTo({top:0, behavior:'smooth'}));
    document.body.appendChild(b);
    window.addEventListener('scroll', () => b.classList.toggle('visible', window.scrollY > 400), {passive:true});
})();

loadWeek();
setInterval(loadWeek, 3e5);
