let allRecommendations = [], allOddsData = {}, currentStake = 0.5, filtersSetUp = false;
let currentFilters = { grade:'all', type:'all', book:'all', sortBy:'edge' };
let currentMode = 'all'; // 'espn' or 'all'
let rawPerformanceData = null;
let profitChartInstance = null, allSortedBets = [], pinnedTooltipIndex = -1;
let allParlays = [], currentParlayFilter = 'all', currentParlaySort = 'ev', parlayChartInstance = null;

const MODE_CONFIG = {
    espn: {
        label: 'ESPN Bet',
        minEdge: 0.03,
        bookFilter: book => book.toLowerCase() === 'espnbet',
        description: 'ESPN Bet Only — 3%+ Edge, Conservative Mode',
    },
    all: {
        label: 'All Books',
        minEdge: 0.03,
        bookFilter: book => !['fanduel','betparx','lowvig','fliff','pinnacle','betcris'].includes(book.toLowerCase()),
        description: 'Soft Books — 3%+ Edge, Conservative Mode',
    }
};

// Filter performance bets by current mode
function filterBetsByMode(bets) {
    const cfg = MODE_CONFIG[currentMode];
    if (currentMode === 'espn') {
        return bets.filter(r => cfg.bookFilter(r.bet.book||''));
    }
    return bets.filter(r => {
        if (!cfg.bookFilter(r.bet.book||'')) return false;
        if ((r.bet.edge||0) < cfg.minEdge) return false;
        return true;
    });
}

// Helpers
const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);
const pct = (v,d=1) => (v*100).toFixed(d)+'%';
const usd = v => '$'+v.toFixed(2);
const signUsd = v => (v>=0?'+':'')+usd(v);
const fmtOdds = o => (o>0?'+':'')+o;

const BOOKS = {fanduel:'FanDuel',draftkings:'DraftKings',betmgm:'BetMGM',caesars:'Caesars',pointsbet:'PointsBet',bet365:'Bet365',pinnacle:'Pinnacle',betrivers:'BetRivers',thescore:'theScore',williamhill:'William Hill',unibet:'Unibet',superbook:'SuperBook',bovada:'Bovada',betonlineag:'BetOnline',lowvig:'LowVig',mybookieag:'MyBookie',betus:'BetUS',wynnbet:'WynnBet',betfred:'BetFred',espnbet:'ESPN Bet',fanatics:'Fanatics',fliff:'Fliff',hardrock:'Hard Rock',ballybet:'Bally Bet',hardrockbet:'Hard Rock Bet'};
const fmtBook = b => BOOKS[b.toLowerCase()] || b.charAt(0).toUpperCase()+b.slice(1);

function getGrade(e) { return e>=.07?'A':e>=.04?'B+':e>=.03?'B':'C+'; }
function getGradeClass(g) { return {A:'grade-a','B+':'grade-b-plus',B:'grade-b','C+':'grade-c-plus'}[g]||'grade-c-plus'; }

// Tabs
function showTab(t) {
    $('today-tab').style.display = $('parlays-tab').style.display = $('performance-tab').style.display = 'none';
    $$('.tab-button').forEach(b => b.classList.remove('active'));
    if (t==='today') { $('today-tab').style.display='block'; $$('.tab-button')[0].classList.add('active'); }
    else if (t==='parlays') { $('parlays-tab').style.display='block'; $$('.tab-button')[1].classList.add('active'); displayParlays(); loadParlayPerformance(); }
    else { $('performance-tab').style.display='block'; $$('.tab-button')[2].classList.add('active'); loadPerformanceData(); }
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
        const ts=Date.now();
        const [rr,hr] = await Promise.all([fetch(`bet_results.json?v=${ts}`),fetch(`analysis_history.json?v=${ts}`)]);
        rawPerformanceData = rr.ok ? await rr.json() : null;
        displayPerformance(rawPerformanceData, hr.ok?await hr.json():null);
    } catch(e) { console.error(e); displayNoPerformanceData(); }
}

function displayPerformance(results) {
    if (!results?.results || !Object.keys(results.results).length) { displayNoPerformanceData(); return; }
    let bets = Object.values(results.results).filter(r=>r.result!=='push');
    bets = filterBetsByMode(bets);
    if (!bets.length) { displayNoPerformanceData(); return; }
    const won = bets.filter(r=>r.result==='won');
    const staked = bets.reduce((s,r)=>s+r.bet.stake,0);
    const profit = bets.reduce((s,r)=>s+r.profit,0);
    const expGain = bets.reduce((s,r)=>s+r.bet.stake*r.bet.edge,0);
    const diff = profit-expGain;

    $('perf-total-bets').textContent = bets.length;
    $('perf-win-rate').textContent = pct(won.length/bets.length);
    $('perf-roi').textContent = pct(profit/staked);
    $('perf-profit').textContent = usd(profit);
    $('expected-gain').textContent = usd(expGain);
    $('actual-gain').textContent = usd(profit);
    const d=$('gain-difference'); d.textContent=signUsd(diff); d.className=`big-number ${diff>=0?'positive':'negative'}`;

    displayGradePerformance(bets);
    displayRecentResults(bets);
    displayProfitChart(bets);
}

function displayGradePerformance(bets) {
    const g = {};
    bets.forEach(r => {
        const gr=getGrade(r.bet.edge);
        if(!g[gr]) g[gr]={bets:[],won:0,staked:0,profit:0};
        g[gr].bets.push(r); g[gr].staked+=r.bet.stake; g[gr].profit+=r.profit;
        if(r.result==='won') g[gr].won++;
    });
    $('grade-performance-list').innerHTML = ['A','B+','B','C+'].filter(k=>g[k]).map(k => {
        const d=g[k], wr=pct(d.won/d.bets.length), roi=pct(d.profit/d.staked), pc=d.profit>=0?'positive':'negative';
        return `<div class="grade-performance-item"><div class="grade-performance-badge ${getGradeClass(k)}">${k}</div><div class="grade-performance-stats">
            <div class="grade-stat"><span class="grade-stat-label">Bets</span><span class="grade-stat-value">${d.bets.length}</span></div>
            <div class="grade-stat"><span class="grade-stat-label">Win Rate</span><span class="grade-stat-value">${wr}</span></div>
            <div class="grade-stat"><span class="grade-stat-label">ROI</span><span class="grade-stat-value ${pc}">${roi}</span></div>
            <div class="grade-stat"><span class="grade-stat-label">Profit</span><span class="grade-stat-value ${pc}">${usd(d.profit)}</span></div>
        </div></div>`;
    }).join('');
}

function displayRecentResults(bets) {
    const sorted = [...bets].sort((a,b) => new Date(b.bet.analysis_timestamp||b.checked_at||0)-new Date(a.bet.analysis_timestamp||a.checked_at||0));
    $('recent-results-list').innerHTML = sorted.slice(0,20).map(r => {
        const gc=getGradeClass(getGrade(r.bet.edge));
        const icon = r.result==='won'?'✅':r.result==='push'?'➖':'❌';
        const d = new Date(r.bet.analysis_timestamp||r.checked_at);
        return `<div class="result-item"><div class="result-icon">${icon}</div><div class="result-details">
            <div class="result-pick">${r.bet.pick}</div><div class="result-game">${r.bet.game}</div></div>
            <div class="result-date">${d.toLocaleDateString('en-US',{month:'short',day:'numeric'})}</div>
            <div class="result-grade ${gc}">${getGrade(r.bet.edge)}</div>
            <div class="result-profit ${r.profit>=0?'positive':'negative'}">${signUsd(r.profit)}</div></div>`;
    }).join('');
}

// Chart
function displayProfitChart(bets) {
    allSortedBets = [...bets].sort((a,b) => new Date(a.bet.analysis_timestamp||a.checked_at||0)-new Date(b.bet.analysis_timestamp||b.checked_at||0));
    renderProfitChart(allSortedBets);
}

function setChartRange(range) {
    $$('.range-btn').forEach(b=>b.classList.remove('active'));
    document.querySelector(`.range-btn[data-range="${range}"]`).classList.add('active');
    dismissPinnedTooltip();
    if (range==='all'||!allSortedBets.length) { renderProfitChart(allSortedBets); return; }
    const ms = {day:864e5,week:6048e5,month:2592e6}[range];
    const cutoff = new Date(Date.now()-ms);
    renderProfitChart(allSortedBets.filter(r=>new Date(r.bet.analysis_timestamp||r.checked_at||0)>=cutoff),0,0);
}

function dismissPinnedTooltip() {
    pinnedTooltipIndex=-1;
    document.querySelector('.chart-tooltip-pinned')?.remove();
}

function showPinnedTooltip(chart,idx,chartBets) {
    dismissPinnedTooltip(); pinnedTooltipIndex=idx;
    const bet=chartBets[idx]; if(!bet) return;
    const pt=chart.getDatasetMeta(0).data[idx]; if(!pt) return;
    const cont=chart.canvas.parentElement;
    const d=new Date(bet.bet.analysis_timestamp||bet.checked_at);
    const p=chart.data.datasets[0].data[idx], e=chart.data.datasets[1].data[idx];
    const tt=document.createElement('div'); tt.className='chart-tooltip-pinned';
    tt.innerHTML=`<button class="tooltip-close" onclick="dismissPinnedTooltip()">&times;</button>
        <div class="tooltip-title">${d.toLocaleDateString('en-US',{month:'short',day:'numeric'})} — ${bet.result==='won'?'W':'L'}</div>
        <div class="tooltip-line"><span>${bet.bet.pick}</span></div>
        <div class="tooltip-line"><span style="color:var(--text-muted)">${bet.bet.game}</span></div>
        <div class="tooltip-line"><span>P/L:</span><span style="color:var(${bet.profit>=0?'--green':'--red'})">${signUsd(bet.profit)}</span></div>
        <div class="tooltip-line"><span>Cumulative:</span><span>${usd(p)}</span></div>
        <div class="tooltip-line"><span>Expected:</span><span style="color:var(--mlb-red)">${usd(e)}</span></div>`;
    let l=pt.x-120, t=pt.y-140;
    if(l<0) l=pt.x+10; if(l+240>cont.offsetWidth) l=pt.x-250; if(t<0) t=pt.y+10;
    tt.style.left=l+'px'; tt.style.top=t+'px';
    cont.appendChild(tt);
}

function renderProfitChart(bets,sp=0,se=0) {
    const canvas=$('profit-chart'); if(!canvas||typeof Chart==='undefined') return;
    dismissPinnedTooltip();
    if(!bets.length) {
        if(profitChartInstance) profitChartInstance.destroy();
        const c=canvas.getContext('2d'); c.clearRect(0,0,canvas.width,canvas.height);
        c.fillStyle='#6B7A8D'; c.font='14px sans-serif'; c.textAlign='center';
        c.fillText('No bets in this time range',canvas.width/2,canvas.height/2); return;
    }
    let cp=sp, ce=se; const labels=[],pd=[],ed=[],colors=[],betDates=[];
    bets.forEach(r => {
        cp+=r.profit; ce+=r.bet.stake*r.bet.edge;
        const d=new Date(r.bet.analysis_timestamp||r.checked_at);
        labels.push(d.toLocaleDateString('en-US',{month:'short',day:'numeric'}));
        betDates.push(d.toISOString().slice(0,10));
        pd.push(+cp.toFixed(2)); ed.push(+ce.toFixed(2));
        colors.push(r.result==='won'?'#22C55E':'#EF4444');
    });

    if(profitChartInstance) profitChartInstance.destroy();
    const mob=window.innerWidth<768, chartBets=bets;
    profitChartInstance = new Chart(canvas.getContext('2d'), {
        type:'line',
        data:{labels, datasets:[
            {label:'Actual Profit',data:pd,borderColor:'#C41E3A',backgroundColor:'rgba(196,30,58,.1)',fill:true,tension:.3,borderWidth:2.5,pointRadius:mob?3:4,pointHitRadius:mob?20:8,pointBackgroundColor:colors,pointBorderColor:colors,pointBorderWidth:0},
            {label:'Expected (EV)',data:ed,borderColor:'#F4901E',borderDash:[6,3],borderWidth:1.5,pointRadius:0,fill:false,tension:.3}
        ]},
        options:{
            responsive:true, maintainAspectRatio:false,
            interaction:{intersect:false,mode:'index'},
            onClick(ev,els) {
                if(els.length) { const i=els[0].index; pinnedTooltipIndex===i?dismissPinnedTooltip():showPinnedTooltip(this,i,chartBets); }
                else dismissPinnedTooltip();
            },
            plugins:{
                legend:{display:true,position:'top',labels:{color:'#B8C4D0',font:{size:mob?10:12},usePointStyle:true,padding:mob?10:16}},
                tooltip:{enabled:!mob,backgroundColor:'rgba(20,25,35,.95)',titleColor:'#E8EDF2',bodyColor:'#B8C4D0',borderColor:'rgba(255,255,255,.1)',borderWidth:1,padding:10,
                    callbacks:{afterBody(ctx){const b=chartBets[ctx[0].dataIndex];if(!b)return'';return `${b.result==='won'?'W':'L'}: ${b.bet.pick} (${b.bet.game})\nP/L: ${signUsd(b.profit)}`;}}
                }
            },
            scales:{
                x:{ticks:{color:'#6B7A8D',font:{size:mob?9:10},maxRotation:45,maxTicksLimit:mob?8:20},grid:{color:'rgba(255,255,255,.05)'}},
                y:{ticks:{color:'#6B7A8D',callback:v=>usd(v),font:{size:mob?9:11}},grid:{color:'rgba(255,255,255,.05)'},title:{display:!mob,text:'Cumulative Profit ($)',color:'#6B7A8D'}}
            }
        }
    });
}

function displayNoPerformanceData() {
    ['grade-performance-list','recent-results-list'].forEach(id => {
        $(id).innerHTML=`<div class="no-data"><div class="no-data-icon">📊</div><p>No performance data yet.</p><p style="font-size:.82rem;margin-top:6px">Run <code>python bet_tracker.py --check</code></p></div>`;
    });
    ['perf-total-bets','perf-win-rate','perf-roi','perf-profit'].forEach((id,i)=>$(id).textContent=['0','-','-','$0.00'][i]);
    ['expected-gain','actual-gain','gain-difference'].forEach(id=>$(id).textContent='$0.00');
}

// Analysis display
function displayAnalysis(data) {
    const ts=new Date(data.timestamp);
    $('timestamp').textContent=ts.toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZone:'America/New_York'})+' EST';
    $('games-analyzed').textContent=data.games_analyzed.length;
    $('bets-found').textContent=data.recommendations.length;
    if(data.recommendations.length) {
        const tot=data.recommendations.length*data.stake;
        $('expected-roi').textContent=pct(data.recommendations.reduce((s,b)=>s+b.ev,0)/tot);
    } else $('expected-roi').textContent='N/A';

    allRecommendations=data.recommendations; currentStake=data.stake||0.5; allOddsData=data.all_odds||{};
    allParlays = data.parlays || [];
    $('parlays-stake').textContent = usd(currentStake);
    populateBookFilter(allRecommendations); setupFilters();
    displayRecommendations(allRecommendations,currentStake);
    displayGames(data.games_analyzed);
}

// Mode switch
function setMode(mode) {
    currentMode = mode;
    $$('.mode-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.mode-btn[data-mode="${mode}"]`).classList.add('active');
    const sub = document.querySelector('.subtitle');
    if (sub) sub.textContent = MODE_CONFIG[mode].description;
    populateBookFilter(allRecommendations);
    currentFilters.book = 'all';
    const bookSel = $('filter-book');
    if (bookSel) bookSel.value = 'all';
    applyFilters();
    if ($('performance-tab').style.display !== 'none' && rawPerformanceData) {
        displayPerformance(rawPerformanceData);
    }
}

// Filters
function setupFilters() {
    if(filtersSetUp) return; filtersSetUp=true;
    ['filter-grade','filter-type','filter-book','sort-by'].forEach(id => {
        $(id).addEventListener('change',e => { currentFilters[{['filter-grade']:'grade',['filter-type']:'type',['filter-book']:'book',['sort-by']:'sortBy'}[id]]=e.target.value; applyFilters(); });
    });
}

function applyFilters() {
    const cfg = MODE_CONFIG[currentMode];
    let f=[...allRecommendations];
    f = f.filter(b => cfg.bookFilter(b.book));
    f = f.filter(b => b.edge >= cfg.minEdge);
    if(currentFilters.grade!=='all') f=f.filter(b=>getGrade(b.edge)===currentFilters.grade);
    if(currentFilters.type!=='all') f=f.filter(b=>b.bet_type===currentFilters.type);
    if(currentFilters.book!=='all') f=f.filter(b=>b.book===currentFilters.book);
    const sorts={edge:(a,b)=>b.edge-a.edge,roi:(a,b)=>b.roi-a.roi,confidence:(a,b)=>b.confidence-a.confidence,
        book:(a,b)=>a.book==='thescore'?-1:b.book==='thescore'?1:a.book.localeCompare(b.book)};
    f.sort(sorts[currentFilters.sortBy]||sorts.edge);
    const betsFound = $('bets-found');
    if (betsFound) betsFound.textContent = f.length;
    displayRecommendations(f,currentStake);
}

function populateBookFilter(recs) {
    const cfg = MODE_CONFIG[currentMode];
    const sel=$('filter-book'), books=[...new Set(recs.filter(b => cfg.bookFilter(b.book)).map(b=>b.book))].sort();
    sel.innerHTML='<option value="all">All Books</option>';
    if(books.includes('thescore')) sel.innerHTML+=`<option value="thescore">theScore Bet</option>`;
    books.filter(b=>b!=='thescore').forEach(b => { sel.innerHTML+=`<option value="${b}">${fmtBook(b)}</option>`; });
}

// Bet card rendering
function betMetric(label,val,cls='') { return `<div class="key-metric"><div class="key-metric-label">${label}</div><div class="key-metric-value ${cls}">${val}</div></div>`; }
function detailInline(label,val) { return `<div class="detail-item-inline"><span class="detail-label">${label}</span><span class="detail-value">${val}</span></div>`; }
function compactStat(label,val,cls='') { return `<div class="compact-stat"><span class="compact-stat-label">${label}</span><span class="compact-stat-value ${cls}">${val}</span></div>`; }

function displayRecommendations(recs,stake) {
    const c=$('recommendations-list');
    if(!recs.length) { c.innerHTML=`<div class="no-data" style="padding:24px"><p style="color:var(--text-muted)">No +EV bets match your criteria.</p></div>`; return; }
    const compact=$('view-toggle')?.dataset.view==='compact';
    c.innerHTML = recs.map((b,i) => {
        const g=getGrade(b.edge), gc=getGradeClass(g);
        if(compact) return `<div class="bet-card-compact" onclick="toggleBetCard(this)"><div class="compact-left"><span class="grade ${gc}">${g}</span><span class="bet-pick">${b.pick}</span><span class="compact-game">${b.game}</span></div><div class="compact-stats">
            ${compactStat('Edge',pct(b.edge),'edge-val')}${compactStat('ROI',pct(b.roi),'roi-val')}${compactStat('Odds',fmtOdds(b.odds),'odds-val')}${compactStat('Book',fmtBook(b.book))}${compactStat('Model',pct(b.true_prob))}${compactStat('Implied',pct(b.implied_prob))}${compactStat('Conf',pct(b.confidence,0))}
        </div></div>`;
        return `<div class="bet-card expanded"><div class="bet-header" onclick="toggleBetCard(this.parentElement)"><div><span class="grade ${gc}">${g}</span><span class="bet-pick">${b.pick}</span></div><span style="font-size:.78rem;color:var(--text-muted);font-weight:500">${b.game}</span></div><div class="bet-body">
            <div class="bet-key-metrics">${betMetric('Edge',pct(b.edge),'edge-val')}${betMetric('ROI',pct(b.roi),'roi-val')}${betMetric('EV / '+usd(stake),usd(b.stake*b.roi),'ev-val')}${betMetric('Best Odds',fmtOdds(b.odds),'odds-val')}</div>
            <div class="bet-details-inline">${detailInline('Type',b.bet_type)}${detailInline('Best Book',fmtBook(b.book))}${detailInline('Model Prob',pct(b.true_prob))}${detailInline('Implied Prob',pct(b.implied_prob))}${detailInline('Confidence',pct(b.confidence,0))}</div>
            ${renderLineShopping(b)}</div></div>`;
    }).join('');
}

function toggleBetCard(el) { el.classList.toggle('expanded'); }

function renderLineShopping(bet) {
    const list=bet.all_book_odds||[]; if(list.length<=1) return '';
    const best=list[0].odds;
    return `<div class="line-shopping"><div class="line-shopping-header"><span class="line-shopping-title">Line Shopping</span></div><div class="line-shopping-grid">${list.map(it => {
        const isBest=it.odds===best, pt=it.point!==undefined?` (${it.point})`:'';
        return `<div class="line-shop-item ${isBest?'best-odds':''}"><span class="line-shop-book">${fmtBook(it.book)}</span><span><span class="line-shop-odds">${fmtOdds(it.odds)}${pt}</span>${isBest?'<span class="line-shop-best-tag">Best</span>':''}</span></div>`;
    }).join('')}</div></div>`;
}

function toggleView() {
    const b=$('view-toggle'), next=b.dataset.view==='full'?'compact':'full';
    b.dataset.view=next; b.textContent=next==='compact'?'Full View':'Compact View'; applyFilters();
}

// Game analysis
function displayGames(games) {
    $('games-list').innerHTML = games.map((g,i) => {
        const mp=g.model_probs, mk=g.market_probs, bp=g.blended_probs||mp, ci=g.context_indicators||{};
        const teamLine = (lbl,probs) => `<div class="game-stat"><div class="game-stat-label">${lbl}</div><div class="game-stat-value">${g.home}: ${pct(probs.home_win_prob)}<br>${g.away}: ${pct(probs.away_win_prob)}</div></div>`;
        return `<div class="game-card" onclick="toggleGameDetails(${i})"><div class="game-header">${g.game}${(g.n_bets||0)>0?`<span style="color:var(--mlb-red);font-size:.82rem;font-weight:600"> · ${g.n_bets} +EV bet${g.n_bets>1?'s':''}</span>`:''}</div>
            ${renderContextIndicators(ci)}
            <div class="game-stats">${teamLine('Model Prediction',mp)}${mk?teamLine('Market Odds',mk)+teamLine('Blended',bp):''}
                <div class="game-stat"><div class="game-stat-label">Expected Total</div><div class="game-stat-value">${mp.expected_total?mp.expected_total.toFixed(1):'-'} runs${mp.total_line?`<br><span style="font-size:.78rem;color:var(--text-muted)">Line: ${mp.total_line}</span>`:''}</div></div>
                <div class="game-stat"><div class="game-stat-label">Model Confidence</div><div class="game-stat-value">${pct(mp.confidence||0,0)}<div class="confidence-bar"><div class="confidence-fill" style="width:${(mp.confidence||0)*100}%"></div></div></div></div>
                <div class="game-stat"><div class="game-stat-label">Similar Games</div><div class="game-stat-value">${g.n_similar||mp.n_games||'-'} games</div></div>
            </div><div class="game-details-expanded" id="game-details-${i}">${renderGameDetails(g)}</div></div>`;
    }).join('');
}

function renderContextIndicators(ci) {
    if(!ci||!Object.keys(ci).length) return '';
    const b=[];
    (ci.fatigue||[]).forEach(i => { b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${i.type==='B2B'?'😴':'💪'}</span>${i.team} ${i.type==='B2B'?'B2B':'Rested'}</span>`); });
    (ci.pitcher||[]).forEach(i => { const icon=i.type==='ace'?'🔥':'⚠️'; b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${icon}</span>${i.team} ${i.type==='ace'?'Ace':'Weak SP'} (${i.value.toFixed(0)})</span>`); });
    (ci.park||[]).forEach(i => { const icon=i.type==='hitter-friendly'?'🏟️':'⚾'; b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${icon}</span>${i.type} (${i.value})</span>`); });
    (ci.splits||[]).forEach(i => { const t={strong_home:'Strong Home',weak_home:'Weak Home',strong_road:'Strong Road',weak_road:'Weak Road'}[i.type]; b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${i.severity==='positive'?'🏠':'🛣️'}</span>${i.team} ${t}</span>`); });
    return b.length?`<div class="context-indicators">${b.join('')}</div>`:'';
}

function renderGameDetails(g) {
    let h='';
    // Pitcher matchup
    const pm=g.pitcher_matchup;
    if(pm?.home&&pm?.away) {
        const pc = (t,label) => `<div class="goalie-card"><div class="goalie-name">${label}: ${t.name} (${t.handedness}HP)</div><div class="goalie-stats">
            <div class="goalie-stat-row"><span class="goalie-stat-label">ERA</span><span class="goalie-stat-value">${t.era.toFixed(2)}</span></div>
            <div class="goalie-stat-row"><span class="goalie-stat-label">WHIP</span><span class="goalie-stat-value">${t.whip.toFixed(2)}</span></div>
            <div class="goalie-stat-row"><span class="goalie-stat-label">K/9</span><span class="goalie-stat-value">${t.k_per_9.toFixed(1)}</span></div>
            <div class="goalie-stat-row"><span class="goalie-stat-label">FIP</span><span class="goalie-stat-value">${t.fip.toFixed(2)}</span></div>
        </div><div class="quality-score">${t.quality_score.toFixed(0)}</div></div>`;
        h+=`<div class="details-section"><h3>Pitcher Matchup</h3><div class="goalie-comparison">${pc(pm.home,g.home)}${pc(pm.away,g.away)}</div></div>`;
    }
    // Home/Road splits
    const sp=g.team_splits;
    if(sp?.home&&sp?.away) {
        const sc = (lbl,d) => `<div class="split-card"><div class="split-title">${lbl}</div><div class="split-stats">
            <div class="split-stat-row"><span class="split-stat-label">Win %</span><span class="split-stat-value">${pct(d.win_pct||0)}</span></div>
            <div class="split-stat-row"><span class="split-stat-label">RS/G</span><span class="split-stat-value">${(d.rs_pg||0).toFixed(2)}</span></div>
            <div class="split-stat-row"><span class="split-stat-label">RA/G</span><span class="split-stat-value">${(d.ra_pg||0).toFixed(2)}</span></div>
        </div></div>`;
        h+=`<div class="details-section"><h3>Home/Road Splits (Last 10)</h3><div class="splits-comparison">${sc(g.home+' at Home',sp.home)}${sc(g.away+' on Road',sp.away)}</div></div>`;
    }
    // Bullpen
    if(g.bullpen?.home&&g.bullpen?.away) {
        h+=`<div class="details-section"><h3>Bullpen Quality</h3><div class="advanced-stats-grid">
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.home} BP ERA</div><div class="advanced-stat-value">${(g.bullpen.home.bullpen_era||4).toFixed(2)}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.away} BP ERA</div><div class="advanced-stat-value">${(g.bullpen.away.bullpen_era||4).toFixed(2)}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.home} BP Quality</div><div class="advanced-stat-value">${(g.bullpen.home.bullpen_quality||50).toFixed(0)}</div></div>
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.away} BP Quality</div><div class="advanced-stat-value">${(g.bullpen.away.bullpen_quality||50).toFixed(0)}</div></div>
        </div></div>`;
    }
    // Park factor
    if(g.park_factor) {
        h+=`<div class="details-section"><h3>Park Factor</h3><div class="advanced-stats-grid">
            <div class="advanced-stat-card"><div class="advanced-stat-label">${g.home} Park</div><div class="advanced-stat-value">${g.park_factor}</div></div>
        </div></div>`;
    }
    return h;
}

function toggleGameDetails(i) { $$('.game-card')[i].classList.toggle('expanded'); }

// --- PARLAY FUNCTIONS ---
function filterParlays(f) {
    currentParlayFilter = f;
    $$('.parlay-filter-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === f));
    displayParlays();
}

function sortParlays(s) { currentParlaySort = s; displayParlays(); }

function displayParlays() {
    if (!allParlays.length) {
        $('parlays-list').innerHTML = `<div class="no-data"><div class="no-data-icon">🎰</div><p>No parlays available for today's games.</p><p style="font-size:.82rem;margin-top:6px;color:var(--t3)">Need 2+ eligible bets (ML <+130 or Overs with 3%+ edge)</p></div>`;
        $('parlays-count').textContent = '0';
        $('parlays-best-ev').textContent = '-';
        $('parlays-best-odds').textContent = '-';
        return;
    }

    let filtered = [...allParlays];
    if (currentParlayFilter !== 'all') filtered = filtered.filter(p => p.n_legs === parseInt(currentParlayFilter));

    const sorts = {
        ev: (a, b) => b.ev - a.ev,
        odds: (a, b) => b.combined_odds - a.combined_odds,
        edge: (a, b) => b.edge - a.edge,
        prob: (a, b) => b.combined_true_prob - a.combined_true_prob,
    };
    filtered.sort(sorts[currentParlaySort] || sorts.ev);

    $('parlays-count').textContent = filtered.length;
    if (filtered.length) {
        $('parlays-best-ev').textContent = '$' + filtered.reduce((best, p) => Math.max(best, p.ev), 0).toFixed(4);
        const bestOdds = filtered.reduce((best, p) => p.combined_odds > best ? p.combined_odds : best, -9999);
        $('parlays-best-odds').textContent = (bestOdds > 0 ? '+' : '') + bestOdds;
    }

    $('parlays-list').innerHTML = filtered.map((p, i) => {
        const isTop = i === 0 && currentParlaySort === 'ev';
        const ts = p.datetime ? new Date(p.datetime).toLocaleString('en-US', {month:'short',day:'numeric',hour:'numeric',minute:'2-digit',hour12:true}) : (p.date || '');
        return `<div class="parlay-card ${isTop ? 'parlay-top' : ''}" onclick="this.classList.toggle('expanded')">
            <div class="parlay-header">
                <div>
                    ${isTop ? '<span class="parlay-badge">⭐ BEST</span>' : ''}
                    <span class="parlay-legs-count">${p.n_legs}-Leg Parlay</span>
                    <span style="font-size:.72rem;color:var(--t3);margin-left:8px;">${ts}</span>
                </div>
                <div class="parlay-header-stats">
                    <span class="parlay-odds">${p.combined_odds > 0 ? '+' : ''}${p.combined_odds}</span>
                    <span class="parlay-ev">EV: $${p.ev.toFixed(4)}</span>
                </div>
            </div>
            <div class="parlay-body">
                <div class="parlay-legs-group">${p.legs.map(leg => `
                    <div class="parlay-leg">
                        <div class="parlay-leg-pick">${leg.pick}</div>
                        <div class="parlay-leg-details">
                            <span>${leg.game}</span>
                            <span>${leg.bet_type} · ${fmtBook(leg.book)} · ${leg.odds > 0 ? '+' : ''}${leg.odds}</span>
                            <span>Edge: ${pct(leg.edge)} · Model: ${pct(leg.true_prob)}</span>
                        </div>
                    </div>`).join('')}
                </div>
                <div class="parlay-summary">
                    <div class="parlay-summary-stat"><span>Win Prob</span><span>${pct(p.combined_true_prob)}</span></div>
                    <div class="parlay-summary-stat"><span>Implied Prob</span><span>${pct(p.combined_implied_prob)}</span></div>
                    <div class="parlay-summary-stat"><span>Edge</span><span class="edge-val">${pct(p.edge)}</span></div>
                    <div class="parlay-summary-stat"><span>Payout</span><span class="roi-val">$${p.payout.toFixed(2)}</span></div>
                    <div class="parlay-summary-stat"><span>ROI</span><span class="roi-val">${pct(p.roi)}</span></div>
                </div>
            </div>
        </div>`;
    }).join('');
}

async function loadParlayPerformance() {
    try {
        const r = await fetch(`parlay_results.json?v=${Date.now()}`);
        if (!r.ok) { hideParlayPerf(); return; }
        const data = await r.json();
        displayParlayPerformance(data);
    } catch (e) { hideParlayPerf(); }
}

function hideParlayPerf() { $('parlay-perf-section').style.display = 'none'; }

function displayParlayPerformance(data) {
    if (!data || !data.total_parlays) { hideParlayPerf(); return; }
    $('parlay-perf-section').style.display = 'block';

    const profitClass = data.total_profit >= 0 ? 'positive' : 'negative';
    $('parlay-perf-stats').innerHTML = `
        <div class="stat"><span class="stat-label">Total Parlays</span><span class="stat-value">${data.total_parlays}</span></div>
        <div class="stat"><span class="stat-label">Win Rate</span><span class="stat-value">${pct(data.win_rate)}</span></div>
        <div class="stat"><span class="stat-label">ROI</span><span class="stat-value ${profitClass}">${pct(data.roi)}</span></div>
        <div class="stat"><span class="stat-label">Profit</span><span class="stat-value ${profitClass}">${signUsd(data.total_profit)}</span></div>`;

    // Legs breakdown
    if (data.by_legs) {
        $('parlay-legs-breakdown').innerHTML = '<h3 style="color:var(--t2);font-size:.78rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px;">By Leg Count</h3>' +
            Object.entries(data.by_legs).map(([n, d]) => {
                const pc = d.profit >= 0 ? 'positive' : 'negative';
                return `<div class="grade-performance-item"><div class="grade-performance-badge grade-b">${n}L</div><div class="grade-performance-stats">
                    <div class="grade-stat"><span class="grade-stat-label">Parlays</span><span class="grade-stat-value">${d.total}</span></div>
                    <div class="grade-stat"><span class="grade-stat-label">Win Rate</span><span class="grade-stat-value">${pct(d.win_rate)}</span></div>
                    <div class="grade-stat"><span class="grade-stat-label">ROI</span><span class="grade-stat-value ${pc}">${pct(d.roi)}</span></div>
                    <div class="grade-stat"><span class="grade-stat-label">Profit</span><span class="grade-stat-value ${pc}">${signUsd(d.profit)}</span></div>
                </div></div>`;
            }).join('');
    }

    // Recent parlay results
    if (data.parlays?.length) {
        const recent = data.parlays.slice(0, 15);
        $('parlay-recent-results').innerHTML = '<h3 style="color:var(--t2);font-size:.78rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px;">Recent Parlays</h3>' +
            recent.map(p => {
                const icon = p.result === 'won' ? '✅' : '❌';
                const legs = p.legs.map(l => l.pick).join(' + ');
                const ts = p.datetime ? new Date(p.datetime).toLocaleString('en-US', {month:'short',day:'numeric',hour:'numeric',minute:'2-digit',hour12:true}) : p.date;
                const legDetail = p.legs.map(l => {
                    const res = l.result === 'won' ? '✓' : '✗';
                    return `<span style="color:${l.result==='won'?'#22C55E':'#EF4444'}">${res} ${l.pick} (${l.odds>0?'+':''}${l.odds})</span>`;
                }).join('<span style="color:var(--t3)"> + </span>');
                return `<div class="result-item" style="grid-template-columns:36px 1fr auto;gap:8px;align-items:start;">
                    <div class="result-icon" style="padding-top:2px;">${icon}</div>
                    <div class="result-details">
                        <div class="result-pick" style="font-size:.82rem;line-height:1.4;">${legDetail}</div>
                        <div class="result-game" style="margin-top:3px;">${ts} · ${p.n_legs}-leg · ${p.combined_odds > 0 ? '+' : ''}${p.combined_odds}${p.ev != null ? ' · EV: $'+p.ev.toFixed(3) : ''}</div>
                    </div>
                    <div class="result-profit ${p.profit >= 0 ? 'positive' : 'negative'}">${signUsd(p.profit)}</div>
                </div>`;
            }).join('');

        // Cumulative profit chart
        renderParlayProfitChart(data.parlays);
    }
}

function renderParlayProfitChart(parlays) {
    const canvas = $('parlay-profit-chart');
    if (!canvas || typeof Chart === 'undefined') return;
    const sorted = [...parlays].sort((a, b) => a.date.localeCompare(b.date));
    if (!sorted.length) return;

    let cp = 0;
    const labels = [], pd = [], colors = [], parlayMeta = [];
    sorted.forEach(p => {
        cp += p.profit;
        const ts = p.datetime ? new Date(p.datetime).toLocaleString('en-US', {month:'short',day:'numeric',hour:'numeric',minute:'2-digit',hour12:true}) : p.date;
        labels.push(ts);
        pd.push(+cp.toFixed(2));
        colors.push(p.result === 'won' ? '#22C55E' : '#EF4444');
        parlayMeta.push({
            result: p.result,
            profit: p.profit,
            odds: p.combined_odds,
            legs: p.legs.map(l => `${l.result==='won'?'✓':'✗'} ${l.pick} (${l.odds>0?'+':''}${l.odds})`),
        });
    });

    if (parlayChartInstance) parlayChartInstance.destroy();
    parlayChartInstance = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { labels, datasets: [{
            label: 'Parlay Profit', data: pd,
            borderColor: '#C41E3A', backgroundColor: 'rgba(196,30,58,.1)',
            fill: true, tension: .3, borderWidth: 2.5,
            pointRadius: 4, pointBackgroundColor: colors, pointBorderColor: colors, pointBorderWidth: 0,
        }]},
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(20,25,35,.95)', titleColor: '#E8EDF2', bodyColor: '#B8C4D0',
                    callbacks: {
                        title: ctx => labels[ctx[0].dataIndex],
                        afterTitle: ctx => {
                            const m = parlayMeta[ctx[0].dataIndex];
                            return `${m.result === 'won' ? '✅ WON' : '❌ LOST'} · ${m.odds > 0 ? '+' : ''}${m.odds}`;
                        },
                        label: ctx => `Cumulative: ${usd(ctx.parsed.y)}`,
                        afterLabel: ctx => {
                            const m = parlayMeta[ctx.dataIndex];
                            return [`Bet: ${signUsd(m.profit)}`, ...m.legs];
                        },
                    }
                }
            },
            scales: {
                x: { ticks: { color: '#6B7A8D', font: { size: 10 }, maxRotation: 45, maxTicksLimit: 15 }, grid: { color: 'rgba(255,255,255,.05)' }},
                y: { ticks: { color: '#6B7A8D', callback: v => usd(v) }, grid: { color: 'rgba(255,255,255,.05)' }, title: { display: true, text: 'Cumulative Profit ($)', color: '#6B7A8D' }}
            }
        }
    });
}

// Scroll-to-top
(function(){
    const b=document.createElement('button'); b.className='scroll-top-btn'; b.innerHTML='↑'; b.setAttribute('aria-label','Scroll to top');
    b.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));
    document.body.appendChild(b);
    window.addEventListener('scroll',()=>b.classList.toggle('visible',window.scrollY>400),{passive:true});
})();

// Resize handler
let resizeT; window.addEventListener('resize',()=>{clearTimeout(resizeT);resizeT=setTimeout(()=>{if(profitChartInstance&&allSortedBets.length) setChartRange(document.querySelector('.range-btn.active')?.dataset.range||'all');},250);});

loadAnalysis();
setInterval(loadAnalysis,3e5);
