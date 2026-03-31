let allRecommendations = [], allOddsData = {}, currentStake = 1, filtersSetUp = false;
let currentFilters = { grade:'all', type:'all', book:'all', sortBy:'edge' };
let profitChartInstance = null, allSortedBets = [], pinnedTooltipIndex = -1;

// Model changes — dates when the +EV calculation logic was materially changed
const MODEL_CHANGES = [
    { date:'2026-03-06', label:'Optimize model', desc:'Model parameter tuning' },
    { date:'2026-03-08', label:'Add ML + injuries', desc:'XGBoost ML model, auto-retrain, injury impact scoring' },
    { date:'2026-03-11', label:'Change blend', desc:'Adjusted model vs market blend weights' },
    { date:'2026-03-14', label:'Fix totals + injuries', desc:'Poisson for alt lines, .5-only filter, reduced injury coeff 75%' },
    { date:'2026-03-16', label:'6 degradation fixes', desc:'Recency weighting, Under bias 1.67x, sharp book filter, daily retrain, model weight 55→65%, time-decay similarity' },
    { date:'2026-03-22', label:'Block .0 lines', desc:'Remove whole-number total lines (push risk), rebuild injury scoring' },
];

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
    $('today-tab').style.display = $('performance-tab').style.display = 'none';
    $$('.tab-button').forEach(b => b.classList.remove('active'));
    if (t==='today') { $('today-tab').style.display='block'; $$('.tab-button')[0].classList.add('active'); }
    else { $('performance-tab').style.display='block'; $$('.tab-button')[1].classList.add('active'); loadPerformanceData(); }
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
        displayPerformance(rr.ok?await rr.json():null, hr.ok?await hr.json():null);
    } catch(e) { console.error(e); displayNoPerformanceData(); }
}

function displayPerformance(results) {
    if (!results?.results || !Object.keys(results.results).length) { displayNoPerformanceData(); return; }
    const bets = Object.values(results.results).filter(r=>r.result!=='push');
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
        <div class="tooltip-line"><span style="color:var(--t3)">${bet.bet.game}</span></div>
        <div class="tooltip-line"><span>P/L:</span><span style="color:var(${bet.profit>=0?'--grn':'--red'})">${signUsd(bet.profit)}</span></div>
        <div class="tooltip-line"><span>Cumulative:</span><span>${usd(p)}</span></div>
        <div class="tooltip-line"><span>Expected:</span><span style="color:var(--orange)">${usd(e)}</span></div>`;
    let l=pt.x-120, t=pt.y-140;
    if(l<0) l=pt.x+10; if(l+240>cont.offsetWidth) l=pt.x-250; if(t<0) t=pt.y+10;
    tt.style.left=l+'px'; tt.style.top=t+'px';
    cont.appendChild(tt);
}

function showModelChangeTooltip(chart,mc) {
    dismissPinnedTooltip(); pinnedTooltipIndex=-2; // special value for model change
    const cont=chart.canvas.parentElement;
    const x=chart.scales.x.getPixelForValue(mc.idx);
    const tt=document.createElement('div'); tt.className='chart-tooltip-pinned';
    tt.style.borderColor='var(--orange)';
    tt.innerHTML=`<button class="tooltip-close" onclick="dismissPinnedTooltip()">&times;</button>
        <div class="tooltip-title" style="color:var(--orange)">🔧 Model Change — ${mc.date}</div>
        <div class="tooltip-line" style="font-weight:700">${mc.label}</div>
        <div class="tooltip-line" style="color:var(--t2);font-size:.78rem">${mc.desc}</div>`;
    let l=x-120, t=40;
    if(l<0) l=x+10; if(l+240>cont.offsetWidth) l=x-250;
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
        betDates.push(d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'));
        pd.push(+cp.toFixed(2)); ed.push(+ce.toFixed(2));
        colors.push(r.result==='won'?'#00C896':'#FF4D6A');
    });

    // Find which bet indices correspond to model change dates
    const changeIndices = [];
    MODEL_CHANGES.forEach(mc => {
        // Find first bet ON or AFTER this date
        const idx = betDates.findIndex(d => d >= mc.date);
        if (idx >= 0) changeIndices.push({idx, ...mc});
    });

    // Custom plugin to draw vertical lines at model change points
    const modelChangePlugin = {
        id:'modelChanges',
        afterDraw(chart) {
            const ctx=chart.ctx, xScale=chart.scales.x, yScale=chart.scales.y;
            changeIndices.forEach((mc,i) => {
                const x = xScale.getPixelForValue(mc.idx);
                if (x < xScale.left || x > xScale.right) return;
                // Vertical dashed line
                ctx.save();
                ctx.beginPath(); ctx.setLineDash([4,4]);
                ctx.strokeStyle='rgba(255,255,255,0.25)'; ctx.lineWidth=1;
                ctx.moveTo(x, yScale.top); ctx.lineTo(x, yScale.bottom);
                ctx.stroke(); ctx.setLineDash([]);
                // Label — stagger vertically to avoid overlap
                const yOff = yScale.top + 8 + (i % 3) * 14;
                ctx.font='bold 9px sans-serif'; ctx.fillStyle='rgba(255,255,255,0.7)';
                ctx.textAlign='center';
                // Diamond marker
                ctx.fillStyle='#F4901E'; ctx.beginPath();
                ctx.moveTo(x,yOff); ctx.lineTo(x+4,yOff+4); ctx.lineTo(x,yOff+8); ctx.lineTo(x-4,yOff+4); ctx.closePath(); ctx.fill();
                // Label text
                ctx.fillStyle='rgba(255,255,255,0.6)';
                ctx.fillText(mc.label, x, yOff+18);
                ctx.restore();
            });
        }
    };

    if(profitChartInstance) profitChartInstance.destroy();
    const mob=window.innerWidth<768, chartBets=bets;
    profitChartInstance = new Chart(canvas.getContext('2d'), {
        type:'line',
        data:{labels, datasets:[
            {label:'Actual Profit',data:pd,borderColor:'#007C85',backgroundColor:'rgba(0,124,133,.1)',fill:true,tension:.3,borderWidth:2.5,pointRadius:mob?3:4,pointHitRadius:mob?20:8,pointBackgroundColor:colors,pointBorderColor:colors,pointBorderWidth:0},
            {label:'Expected (EV)',data:ed,borderColor:'#F4901E',borderDash:[6,3],borderWidth:1.5,pointRadius:0,fill:false,tension:.3}
        ]},
        plugins:[modelChangePlugin],
        options:{
            responsive:true, maintainAspectRatio:false,
            interaction:{intersect:false,mode:'index'},
            onClick(ev,els) {
                // Check if click is near a model change marker
                const rect=canvas.getBoundingClientRect();
                const cx=ev.native.clientX-rect.left;
                const xScale=this.scales.x;
                for(const mc of changeIndices) {
                    const mx=xScale.getPixelForValue(mc.idx);
                    if(Math.abs(cx-mx)<15) { showModelChangeTooltip(this,mc); return; }
                }
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

    allRecommendations=data.recommendations; currentStake=data.stake||1; allOddsData=data.all_odds||{};
    populateBookFilter(allRecommendations); setupFilters();
    displayRecommendations(allRecommendations,currentStake);
    displayGames(data.games_analyzed);
}

// Filters
function setupFilters() {
    if(filtersSetUp) return; filtersSetUp=true;
    ['filter-grade','filter-type','filter-book','sort-by'].forEach(id => {
        $(id).addEventListener('change',e => { currentFilters[{['filter-grade']:'grade',['filter-type']:'type',['filter-book']:'book',['sort-by']:'sortBy'}[id]]=e.target.value; applyFilters(); });
    });
}

function applyFilters() {
    let f=[...allRecommendations];
    if(currentFilters.grade!=='all') f=f.filter(b=>getGrade(b.edge)===currentFilters.grade);
    if(currentFilters.type!=='all') f=f.filter(b=>b.bet_type===currentFilters.type);
    if(currentFilters.book!=='all') f=f.filter(b=>b.book===currentFilters.book);
    const sorts={edge:(a,b)=>b.edge-a.edge,roi:(a,b)=>b.roi-a.roi,confidence:(a,b)=>b.confidence-a.confidence,
        book:(a,b)=>a.book==='thescore'?-1:b.book==='thescore'?1:a.book.localeCompare(b.book)};
    f.sort(sorts[currentFilters.sortBy]||sorts.edge);
    displayRecommendations(f,currentStake);
}

function populateBookFilter(recs) {
    const sel=$('filter-book'), books=[...new Set(recs.map(b=>b.book))].sort();
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
    if(!recs.length) { c.innerHTML=`<div class="no-data" style="padding:24px"><p style="color:var(--t3)">No +EV bets match your criteria.</p></div>`; return; }
    const compact=$('view-toggle')?.dataset.view==='compact';
    c.innerHTML = recs.map((b,i) => {
        const g=getGrade(b.edge), gc=getGradeClass(g);
        if(compact) return `<div class="bet-card-compact" onclick="toggleBetCard(this)"><div class="compact-left"><span class="grade ${gc}">${g}</span><span class="bet-pick">${b.pick}</span><span class="compact-game">${b.game}</span></div><div class="compact-stats">
            ${compactStat('Edge',pct(b.edge),'edge-val')}${compactStat('ROI',pct(b.roi),'roi-val')}${compactStat('Odds',fmtOdds(b.odds),'odds-val')}${compactStat('Book',fmtBook(b.book))}${compactStat('Model',pct(b.true_prob))}${compactStat('Implied',pct(b.implied_prob))}${compactStat('Conf',pct(b.confidence,0))}
        </div></div>`;
        return `<div class="bet-card expanded"><div class="bet-header" onclick="toggleBetCard(this.parentElement)"><div><span class="grade ${gc}">${g}</span><span class="bet-pick">${b.pick}</span></div><span style="font-size:.78rem;color:var(--t3);font-weight:500">${b.game}</span></div><div class="bet-body">
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
        return `<div class="game-card" onclick="toggleGameDetails(${i})"><div class="game-header">${g.game}${(g.n_bets||0)>0?`<span style="color:var(--orange);font-size:.82rem;font-weight:600"> · ${g.n_bets} +EV bet${g.n_bets>1?'s':''}</span>`:''}</div>
            ${renderContextIndicators(ci)}
            <div class="game-stats">${teamLine('Model Prediction',mp)}${mk?teamLine('Market Odds',mk)+teamLine('Blended',bp):''}
                <div class="game-stat"><div class="game-stat-label">Expected Total</div><div class="game-stat-value">${mp.expected_total?mp.expected_total.toFixed(1):'-'} goals${mp.total_line?`<br><span style="font-size:.78rem;color:var(--t3)">Line: ${mp.total_line}</span>`:''}</div></div>
                <div class="game-stat"><div class="game-stat-label">Model Confidence</div><div class="game-stat-value">${pct(mp.confidence||0,0)}<div class="confidence-bar"><div class="confidence-fill" style="width:${(mp.confidence||0)*100}%"></div></div></div></div>
                <div class="game-stat"><div class="game-stat-label">Similar Games</div><div class="game-stat-value">${g.n_similar||mp.n_games||'-'} games</div></div>
            </div><div class="game-details-expanded" id="game-details-${i}">${renderGameDetails(g)}</div></div>`;
    }).join('');
}

function renderContextIndicators(ci) {
    if(!ci||!Object.keys(ci).length) return '';
    const b=[];
    (ci.fatigue||[]).forEach(i => { b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${i.type==='B2B'?'😴':'💪'}</span>${i.team} ${i.type==='B2B'?'B2B':'Rested'}</span>`); });
    (ci.goalie||[]).forEach(i => { const m={hot:['positive','🔥','Hot'],cold:['negative','🧊','Cold'],advantage:['positive','🥅','Goalie']}[i.type]; if(m) b.push(`<span class="context-badge ${m[0]}"><span class="context-icon">${m[1]}</span>${i.team} ${m[2]} ${i.type==='advantage'?'+'+i.value.toFixed(0):'.'+((i.value*1000).toFixed(0))}</span>`); });
    (ci.injuries||[]).forEach(i => { b.push(`<span class="context-badge negative"><span class="context-icon">🏥</span>${i.team} Injuries -${i.impact.toFixed(0)}</span>`); });
    (ci.splits||[]).forEach(i => { const t={strong_home:'Strong Home',weak_home:'Weak Home',strong_road:'Strong Road',weak_road:'Weak Road'}[i.type]; b.push(`<span class="context-badge ${i.severity}"><span class="context-icon">${i.severity==='positive'?'🏠':'🛣️'}</span>${i.team} ${t}</span>`); });
    return b.length?`<div class="context-indicators">${b.join('')}</div>`:'';
}

function renderGameDetails(g) {
    let h='';
    const gm=g.goalie_matchup;
    if(gm?.home&&gm?.away) {
        const gc = t => `<div class="goalie-card"><div class="goalie-name">${t===gm.home?g.home:g.away}: ${t.name}</div><div class="goalie-stats">
            <div class="goalie-stat-row"><span class="goalie-stat-label">Recent SV% (L10)</span><span class="goalie-stat-value">.${(t.recent_save_pct*1000).toFixed(0)}</span></div>
            <div class="goalie-stat-row"><span class="goalie-stat-label">Recent GAA (L10)</span><span class="goalie-stat-value">${t.recent_gaa.toFixed(2)}</span></div>
            <div class="goalie-stat-row"><span class="goalie-stat-label">Quality Starts</span><span class="goalie-stat-value">${t.recent_quality_starts}/10</span></div>
        </div><div class="quality-score">${t.quality_score.toFixed(0)}</div></div>`;
        h+=`<div class="details-section"><h3>Goalie Matchup</h3><div class="goalie-comparison">${gc(gm.home)}${gc(gm.away)}</div></div>`;
    }
    const sp=g.team_splits;
    if(sp?.home&&sp?.away) {
        const sc = (t,lbl,d) => `<div class="split-card"><div class="split-title">${lbl}</div><div class="split-stats">
            <div class="split-stat-row"><span class="split-stat-label">Win %</span><span class="split-stat-value">${pct(d.win_pct)}</span></div>
            <div class="split-stat-row"><span class="split-stat-label">GF/G</span><span class="split-stat-value">${d.gf_pg.toFixed(2)}</span></div>
            <div class="split-stat-row"><span class="split-stat-label">GA/G</span><span class="split-stat-value">${d.ga_pg.toFixed(2)}</span></div>
            <div class="split-stat-row"><span class="split-stat-label">Goal Diff</span><span class="split-stat-value">${d.goal_diff>0?'+':''}${d.goal_diff.toFixed(2)}</span></div>
        </div></div>`;
        h+=`<div class="details-section"><h3>Home/Road Splits (Last 10)</h3><div class="splits-comparison">${sc(g.home,g.home+' at Home',sp.home)}${sc(g.away,g.away+' on Road',sp.away)}</div></div>`;
    }
    if(g.injuries&&(g.injuries.home.impact_score>0||g.injuries.away.impact_score>0)) {
        h+=`<div class="details-section"><h3>Injury Impact</h3><div class="injury-list">${[['home',g.home],['away',g.away]].filter(([k])=>g.injuries[k].impact_score>0).map(([k,t])=>`<div class="injury-item"><span class="injury-team">${t}</span><span class="injury-impact">-${g.injuries[k].impact_score.toFixed(1)} impact</span></div>`).join('')}</div></div>`;
    }
    const as=g.advanced_stats;
    if(as?.home&&as?.away) {
        const s=(t,d)=>[['xGF%',d.xGF_pct],['Corsi%',d.corsi_pct],['PDO',d.pdo]].map(([l,v])=>`<div class="advanced-stat-card"><div class="advanced-stat-label">${t} ${l}</div><div class="advanced-stat-value">${v.toFixed(1)}${l!=='PDO'?'%':''}</div></div>`).join('');
        h+=`<div class="details-section"><h3>Advanced Stats</h3><div class="advanced-stats-grid">${s(g.home,as.home)}${s(g.away,as.away)}</div></div>`;
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

// Resize handler
let resizeT; window.addEventListener('resize',()=>{clearTimeout(resizeT);resizeT=setTimeout(()=>{if(profitChartInstance&&allSortedBets.length) setChartRange(document.querySelector('.range-btn.active')?.dataset.range||'all');},250);});

loadAnalysis();
setInterval(loadAnalysis,3e5);
