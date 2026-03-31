// Global state
let allRecommendations = [];
let currentFilters = {
    grade: 'all',
    type: 'all',
    book: 'all',
    sortBy: 'edge'
};

// Tab switching
function showTab(tabName) {
    // Hide all tabs
    document.getElementById('today-tab').style.display = 'none';
    document.getElementById('performance-tab').style.display = 'none';
    
    // Remove active class from all buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    if (tabName === 'today') {
        document.getElementById('today-tab').style.display = 'block';
        document.querySelectorAll('.tab-button')[0].classList.add('active');
    } else if (tabName === 'performance') {
        document.getElementById('performance-tab').style.display = 'block';
        document.querySelectorAll('.tab-button')[1].classList.add('active');
        loadPerformanceData();
    }
}

// Load and display NHL betting analysis
async function loadAnalysis() {
    try {
        console.log('Fetching latest_analysis.json...');
        const response = await fetch('latest_analysis.json');
        console.log('Response status:', response.status, response.statusText);
        
        if (!response.ok) {
            throw new Error(`Failed to load data: ${response.status} ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('Data loaded successfully:', data.timestamp);
        displayAnalysis(data);
        
        document.getElementById('loading').style.display = 'none';
        showTab('today'); // Show today tab after loading
    } catch (error) {
        console.error('Error loading analysis:', error);
        console.error('Error details:', error.message, error.stack);
        document.getElementById('loading').style.display = 'none';
        const errorDiv = document.getElementById('error');
        errorDiv.style.display = 'block';
        errorDiv.innerHTML = `<p>⚠️ Error: ${error.message}</p><p>Check browser console for details.</p>`;
    }
}

// Load performance data
async function loadPerformanceData() {
    try {
        // Add cache busting parameter
        const timestamp = new Date().getTime();
        const [resultsResponse, historyResponse] = await Promise.all([
            fetch(`bet_results.json?v=${timestamp}`),
            fetch(`analysis_history.json?v=${timestamp}`)
        ]);
        
        let results = null;
        let history = null;
        
        if (resultsResponse.ok) {
            results = await resultsResponse.json();
        }
        
        if (historyResponse.ok) {
            history = await historyResponse.json();
        }
        
        displayPerformance(results, history);
    } catch (error) {
        console.error('Error loading performance data:', error);
        displayNoPerformanceData();
    }
}

function displayPerformance(results, history) {
    if (!results || !results.results || Object.keys(results.results).length === 0) {
        displayNoPerformanceData();
        return;
    }
    
    const resolvedBets = Object.values(results.results);
    const wonBets = resolvedBets.filter(r => r.result === 'won');
    
    // Overall stats
    const totalBets = resolvedBets.length;
    const winRate = (wonBets.length / totalBets * 100).toFixed(1);
    const totalStaked = resolvedBets.reduce((sum, r) => sum + r.bet.stake, 0);
    const totalProfit = resolvedBets.reduce((sum, r) => sum + r.profit, 0);
    const roi = (totalProfit / totalStaked * 100).toFixed(1);
    
    document.getElementById('perf-total-bets').textContent = totalBets;
    document.getElementById('perf-win-rate').textContent = `${winRate}%`;
    document.getElementById('perf-roi').textContent = `${roi}%`;
    document.getElementById('perf-profit').textContent = `$${totalProfit.toFixed(2)}`;
    
    // Expected vs Actual
    const expectedGain = resolvedBets.reduce((sum, r) => sum + r.bet.ev, 0);
    const actualGain = totalProfit;
    const difference = actualGain - expectedGain;
    
    document.getElementById('expected-gain').textContent = `$${expectedGain.toFixed(2)}`;
    document.getElementById('actual-gain').textContent = `$${actualGain.toFixed(2)}`;
    
    const diffEl = document.getElementById('gain-difference');
    diffEl.textContent = `${difference >= 0 ? '+' : ''}$${difference.toFixed(2)}`;
    diffEl.className = `big-number ${difference >= 0 ? 'positive' : 'negative'}`;
    
    // Performance by grade
    displayGradePerformance(resolvedBets);
    
    // Recent results
    displayRecentResults(resolvedBets);
}

function displayGradePerformance(resolvedBets) {
    const grades = {};
    
    resolvedBets.forEach(r => {
        const grade = getGrade(r.bet.edge);
        if (!grades[grade]) {
            grades[grade] = { bets: [], won: 0, staked: 0, profit: 0 };
        }
        grades[grade].bets.push(r);
        grades[grade].staked += r.bet.stake;
        grades[grade].profit += r.profit;
        if (r.result === 'won') grades[grade].won++;
    });
    
    const container = document.getElementById('grade-performance-list');
    const gradeOrder = ['A', 'B+', 'B', 'C+'];
    
    container.innerHTML = gradeOrder.filter(g => grades[g]).map(grade => {
        const data = grades[grade];
        const winRate = (data.won / data.bets.length * 100).toFixed(1);
        const roi = (data.profit / data.staked * 100).toFixed(1);
        const gradeClass = getGradeClass(grade);
        
        return `
            <div class="grade-performance-item">
                <div class="grade-performance-badge ${gradeClass}">
                    ${grade}
                </div>
                <div class="grade-performance-stats">
                    <div class="grade-stat">
                        <span class="grade-stat-label">Bets</span>
                        <span class="grade-stat-value">${data.bets.length}</span>
                    </div>
                    <div class="grade-stat">
                        <span class="grade-stat-label">Win Rate</span>
                        <span class="grade-stat-value">${winRate}%</span>
                    </div>
                    <div class="grade-stat">
                        <span class="grade-stat-label">ROI</span>
                        <span class="grade-stat-value ${data.profit >= 0 ? 'positive' : 'negative'}">${roi}%</span>
                    </div>
                    <div class="grade-stat">
                        <span class="grade-stat-label">Profit</span>
                        <span class="grade-stat-value ${data.profit >= 0 ? 'positive' : 'negative'}">$${data.profit.toFixed(2)}</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function displayRecentResults(resolvedBets) {
    const container = document.getElementById('recent-results-list');
    // Sort by checked_at timestamp (most recent first)
    const sorted = [...resolvedBets].sort((a, b) => {
        const dateA = new Date(a.checked_at || a.bet.analysis_timestamp || 0);
        const dateB = new Date(b.checked_at || b.bet.analysis_timestamp || 0);
        return dateB - dateA;
    });
    const recent = sorted.slice(0, 10);
    
    container.innerHTML = recent.map(r => {
        const grade = getGrade(r.bet.edge);
        const gradeClass = getGradeClass(grade);
        const icon = r.result === 'won' ? '✅' : '❌';
        
        return `
            <div class="result-item">
                <div class="result-icon">${icon}</div>
                <div class="result-details">
                    <div class="result-pick">${r.bet.pick}</div>
                    <div class="result-game">${r.bet.game}</div>
                </div>
                <div class="result-grade ${gradeClass}">${grade}</div>
                <div class="result-profit ${r.profit >= 0 ? 'positive' : 'negative'}">
                    ${r.profit >= 0 ? '+' : ''}$${r.profit.toFixed(2)}
                </div>
            </div>
        `;
    }).join('');
}

function displayNoPerformanceData() {
    const sections = ['grade-performance-list', 'recent-results-list'];
    sections.forEach(id => {
        document.getElementById(id).innerHTML = `
            <div class="no-data">
                <div class="no-data-icon">📊</div>
                <p>No performance data yet.</p>
                <p style="font-size: 0.9rem; margin-top: 0.5rem;">
                    Run <code>python bet_tracker.py --check</code> to check bet results.
                </p>
            </div>
        `;
    });
    
    document.getElementById('perf-total-bets').textContent = '0';
    document.getElementById('perf-win-rate').textContent = '-';
    document.getElementById('perf-roi').textContent = '-';
    document.getElementById('perf-profit').textContent = '$0.00';
    document.getElementById('expected-gain').textContent = '$0.00';
    document.getElementById('actual-gain').textContent = '$0.00';
    document.getElementById('gain-difference').textContent = '$0.00';
}

function displayAnalysis(data) {
    // Update summary stats
    const timestamp = new Date(data.timestamp);
    document.getElementById('timestamp').textContent = timestamp.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
    });
    
    document.getElementById('games-analyzed').textContent = data.games_analyzed.length;
    document.getElementById('bets-found').textContent = data.recommendations.length;
    
    // Calculate expected ROI
    if (data.recommendations.length > 0) {
        const totalStake = data.recommendations.length * data.stake;
        const totalEV = data.recommendations.reduce((sum, bet) => sum + bet.ev, 0);
        const roi = (totalEV / totalStake * 100).toFixed(1);
        document.getElementById('expected-roi').textContent = `${roi}%`;
    } else {
        document.getElementById('expected-roi').textContent = 'N/A';
    }
    
    // Store recommendations globally
    allRecommendations = data.recommendations;
    
    // Populate book filter with available books
    populateBookFilter(allRecommendations);
    
    // Setup filter listeners
    setupFilters();
    
    // Display recommendations with current filters
    displayRecommendations(allRecommendations, data.stake);
    
    // Display game analysis
    displayGames(data.games_analyzed);
}

function setupFilters() {
    document.getElementById('filter-grade').addEventListener('change', (e) => {
        currentFilters.grade = e.target.value;
        applyFilters();
    });
    
    document.getElementById('filter-type').addEventListener('change', (e) => {
        currentFilters.type = e.target.value;
        applyFilters();
    });
    
    document.getElementById('filter-book').addEventListener('change', (e) => {
        currentFilters.book = e.target.value;
        applyFilters();
    });
    
    document.getElementById('sort-by').addEventListener('change', (e) => {
        currentFilters.sortBy = e.target.value;
        applyFilters();
    });
}

function applyFilters() {
    let filtered = [...allRecommendations];
    
    // Filter by grade
    if (currentFilters.grade !== 'all') {
        filtered = filtered.filter(bet => getGrade(bet.edge) === currentFilters.grade);
    }
    
    // Filter by type
    if (currentFilters.type !== 'all') {
        filtered = filtered.filter(bet => bet.bet_type === currentFilters.type);
    }
    
    // Filter by book
    if (currentFilters.book !== 'all') {
        filtered = filtered.filter(bet => bet.book === currentFilters.book);
    }
    
    // Sort
    if (currentFilters.sortBy === 'edge') {
        filtered.sort((a, b) => b.edge - a.edge);
    } else if (currentFilters.sortBy === 'roi') {
        filtered.sort((a, b) => b.roi - a.roi);
    } else if (currentFilters.sortBy === 'confidence') {
        filtered.sort((a, b) => b.confidence - a.confidence);
    } else if (currentFilters.sortBy === 'book') {
        // Sort by book name alphabetically, with theScore first
        filtered.sort((a, b) => {
            if (a.book === 'thescore') return -1;
            if (b.book === 'thescore') return 1;
            return a.book.localeCompare(b.book);
        });
    }
    
    displayRecommendations(filtered, 1.0);
}

function populateBookFilter(recommendations) {
    const bookSelect = document.getElementById('filter-book');
    const books = [...new Set(recommendations.map(bet => bet.book))].sort();
    
    // Clear existing options except "All Books"
    bookSelect.innerHTML = '<option value="all">All Books</option>';
    
    // Add theScore first if it exists
    if (books.includes('thescore')) {
        const option = document.createElement('option');
        option.value = 'thescore';
        option.textContent = 'theScore Bet';
        bookSelect.appendChild(option);
    }
    
    // Add other books
    books.filter(book => book !== 'thescore').forEach(book => {
        const option = document.createElement('option');
        option.value = book;
        option.textContent = formatBookName(book);
        bookSelect.appendChild(option);
    });
}

function formatBookName(book) {
    const bookNames = {
        'thescore': 'theScore Bet',
        'draftkings': 'DraftKings',
        'fanduel': 'FanDuel',
        'betmgm': 'BetMGM',
        'caesars': 'Caesars',
        'pointsbet': 'PointsBet',
        'betrivers': 'BetRivers',
        'wynnbet': 'WynnBET',
        'unibet': 'Unibet',
        'espnbet': 'ESPN BET',
        'ballybet': 'Bally Bet',
        'hardrockbet': 'Hard Rock Bet',
        'bovada': 'Bovada'
    };
    return bookNames[book] || book.charAt(0).toUpperCase() + book.slice(1);
}

function displayRecommendations(recommendations, stake) {
    const container = document.getElementById('recommendations-list');
    
    if (recommendations.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #8a9ba8; padding: 20px;">No +EV bets found for today\'s games.</p>';
        return;
    }
    
    // Sort by edge (highest to lowest)
    const sortedRecs = [...recommendations].sort((a, b) => b.edge - a.edge);
    
    container.innerHTML = sortedRecs.map((bet, index) => {
        const grade = getGrade(bet.edge);
        const gradeClass = getGradeClass(grade);
        
        return `
            <div class="bet-card">
                <div class="bet-header">
                    <div>
                        <span class="grade ${gradeClass}">${grade}</span>
                        <span class="bet-pick">${bet.pick}</span>
                    </div>
                </div>
                <div class="bet-details">
                    <div class="detail-item">
                        <span class="detail-label">Game</span>
                        <span class="detail-value">${bet.game}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Type</span>
                        <span class="detail-value">${bet.bet_type}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Book</span>
                        <span class="detail-value">${bet.book}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Odds</span>
                        <span class="detail-value">${bet.odds > 0 ? '+' : ''}${bet.odds}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Edge</span>
                        <span class="detail-value positive">${(bet.edge * 100).toFixed(1)}%</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Model Prob</span>
                        <span class="detail-value">${(bet.true_prob * 100).toFixed(1)}%</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Implied Prob</span>
                        <span class="detail-value">${(bet.implied_prob * 100).toFixed(1)}%</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">EV per $${stake}</span>
                        <span class="detail-value positive">${bet.ev.toFixed(4)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">ROI</span>
                        <span class="detail-value positive">${(bet.roi * 100).toFixed(1)}%</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Confidence</span>
                        <span class="detail-value">${(bet.confidence * 100).toFixed(0)}%</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function displayGames(games) {
    const container = document.getElementById('games-list');
    
    container.innerHTML = games.map((game, index) => {
        const modelProbs = game.model_probs;
        const marketProbs = game.market_probs || null;
        const blendedProbs = game.blended_probs || modelProbs; // Fallback to model if no blended
        const contextIndicators = game.context_indicators || {};
        
        return `
            <div class="game-card" onclick="toggleGameDetails(${index})">
                <div class="game-header">
                    ${game.game}
                    ${game.n_bets > 0 ? `<span style="color: #F4901E; font-size: 0.9rem;"> • ${game.n_bets} +EV bet${game.n_bets > 1 ? 's' : ''}</span>` : ''}
                </div>
                
                ${renderContextIndicators(contextIndicators)}
                
                <div class="game-stats">
                    <div class="game-stat">
                        <div class="game-stat-label">Model Prediction</div>
                        <div class="game-stat-value">
                            ${game.home}: ${(modelProbs.home_win_prob * 100).toFixed(1)}%<br>
                            ${game.away}: ${(modelProbs.away_win_prob * 100).toFixed(1)}%
                        </div>
                    </div>
                    ${marketProbs ? `
                    <div class="game-stat">
                        <div class="game-stat-label">Market Odds</div>
                        <div class="game-stat-value">
                            ${game.home}: ${(marketProbs.home_win_prob * 100).toFixed(1)}%<br>
                            ${game.away}: ${(marketProbs.away_win_prob * 100).toFixed(1)}%
                        </div>
                    </div>
                    <div class="game-stat">
                        <div class="game-stat-label">Blended Prediction</div>
                        <div class="game-stat-value">
                            ${game.home}: ${(blendedProbs.home_win_prob * 100).toFixed(1)}%<br>
                            ${game.away}: ${(blendedProbs.away_win_prob * 100).toFixed(1)}%
                        </div>
                    </div>
                    ` : ''}
                    <div class="game-stat">
                        <div class="game-stat-label">Expected Total</div>
                        <div class="game-stat-value">
                            ${modelProbs.expected_total.toFixed(1)} goals
                            ${modelProbs.total_line ? `<br><span style="font-size: 0.85rem; color: #8a9ba8;">Line: ${modelProbs.total_line}</span>` : ''}
                        </div>
                    </div>
                    <div class="game-stat">
                        <div class="game-stat-label">Model Confidence</div>
                        <div class="game-stat-value">
                            ${(modelProbs.confidence * 100).toFixed(0)}%
                            <div class="confidence-bar">
                                <div class="confidence-fill" style="width: ${modelProbs.confidence * 100}%"></div>
                            </div>
                        </div>
                    </div>
                    <div class="game-stat">
                        <div class="game-stat-label">Similar Games</div>
                        <div class="game-stat-value">${game.n_similar} games</div>
                    </div>
                </div>
                
                <div class="game-details-expanded" id="game-details-${index}">
                    ${renderGameDetails(game)}
                </div>
            </div>
        `;
    }).join('');
}

function renderContextIndicators(indicators) {
    if (!indicators || Object.keys(indicators).length === 0) return '';
    
    let badges = [];
    
    // Fatigue indicators
    if (indicators.fatigue && indicators.fatigue.length > 0) {
        indicators.fatigue.forEach(item => {
            const icon = item.type === 'B2B' ? '😴' : '💪';
            const text = item.type === 'B2B' ? `${item.team} B2B` : `${item.team} Rested`;
            badges.push(`<span class="context-badge ${item.severity}"><span class="context-icon">${icon}</span>${text}</span>`);
        });
    }
    
    // Goalie indicators
    if (indicators.goalie && indicators.goalie.length > 0) {
        indicators.goalie.forEach(item => {
            if (item.type === 'hot') {
                badges.push(`<span class="context-badge positive"><span class="context-icon">🔥</span>${item.team} G Hot (.${(item.value * 1000).toFixed(0)})</span>`);
            } else if (item.type === 'cold') {
                badges.push(`<span class="context-badge negative"><span class="context-icon">🧊</span>${item.team} G Cold (.${(item.value * 1000).toFixed(0)})</span>`);
            } else if (item.type === 'advantage') {
                badges.push(`<span class="context-badge positive"><span class="context-icon">🥅</span>${item.team} Goalie +${item.value.toFixed(0)}</span>`);
            }
        });
    }
    
    // Injury indicators
    if (indicators.injuries && indicators.injuries.length > 0) {
        indicators.injuries.forEach(item => {
            badges.push(`<span class="context-badge negative"><span class="context-icon">🏥</span>${item.team} Injuries -${item.impact.toFixed(0)}</span>`);
        });
    }
    
    // Splits indicators
    if (indicators.splits && indicators.splits.length > 0) {
        indicators.splits.forEach(item => {
            const icon = item.severity === 'positive' ? '🏠' : '🛣️';
            let text = '';
            if (item.type === 'strong_home') text = `${item.team} Strong Home`;
            else if (item.type === 'weak_home') text = `${item.team} Weak Home`;
            else if (item.type === 'strong_road') text = `${item.team} Strong Road`;
            else if (item.type === 'weak_road') text = `${item.team} Weak Road`;
            badges.push(`<span class="context-badge ${item.severity}"><span class="context-icon">${icon}</span>${text}</span>`);
        });
    }
    
    if (badges.length === 0) return '';
    
    return `<div class="context-indicators">${badges.join('')}</div>`;
}

function renderGameDetails(game) {
    let html = '';
    
    // Goalie Matchup
    if (game.goalie_matchup && game.goalie_matchup.home && game.goalie_matchup.away) {
        html += `
            <div class="details-section">
                <h3>🥅 Goalie Matchup</h3>
                <div class="goalie-comparison">
                    <div class="goalie-card">
                        <div class="goalie-name">${game.home}: ${game.goalie_matchup.home.name}</div>
                        <div class="goalie-stats">
                            <div class="goalie-stat-row">
                                <span class="goalie-stat-label">Recent SV% (L10)</span>
                                <span class="goalie-stat-value">.${(game.goalie_matchup.home.recent_save_pct * 1000).toFixed(0)}</span>
                            </div>
                            <div class="goalie-stat-row">
                                <span class="goalie-stat-label">Recent GAA (L10)</span>
                                <span class="goalie-stat-value">${game.goalie_matchup.home.recent_gaa.toFixed(2)}</span>
                            </div>
                            <div class="goalie-stat-row">
                                <span class="goalie-stat-label">Quality Starts</span>
                                <span class="goalie-stat-value">${game.goalie_matchup.home.recent_quality_starts}/10</span>
                            </div>
                        </div>
                        <div class="quality-score">${game.goalie_matchup.home.quality_score.toFixed(0)}</div>
                    </div>
                    <div class="goalie-card">
                        <div class="goalie-name">${game.away}: ${game.goalie_matchup.away.name}</div>
                        <div class="goalie-stats">
                            <div class="goalie-stat-row">
                                <span class="goalie-stat-label">Recent SV% (L10)</span>
                                <span class="goalie-stat-value">.${(game.goalie_matchup.away.recent_save_pct * 1000).toFixed(0)}</span>
                            </div>
                            <div class="goalie-stat-row">
                                <span class="goalie-stat-label">Recent GAA (L10)</span>
                                <span class="goalie-stat-value">${game.goalie_matchup.away.recent_gaa.toFixed(2)}</span>
                            </div>
                            <div class="goalie-stat-row">
                                <span class="goalie-stat-label">Quality Starts</span>
                                <span class="goalie-stat-value">${game.goalie_matchup.away.recent_quality_starts}/10</span>
                            </div>
                        </div>
                        <div class="quality-score">${game.goalie_matchup.away.quality_score.toFixed(0)}</div>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Home/Road Splits
    if (game.team_splits && game.team_splits.home && game.team_splits.away) {
        html += `
            <div class="details-section">
                <h3>🏠 Home/Road Splits (Last 10)</h3>
                <div class="splits-comparison">
                    <div class="split-card">
                        <div class="split-title">${game.home} at Home</div>
                        <div class="split-stats">
                            <div class="split-stat-row">
                                <span class="split-stat-label">Win %</span>
                                <span class="split-stat-value">${(game.team_splits.home.win_pct * 100).toFixed(1)}%</span>
                            </div>
                            <div class="split-stat-row">
                                <span class="split-stat-label">GF/G</span>
                                <span class="split-stat-value">${game.team_splits.home.gf_pg.toFixed(2)}</span>
                            </div>
                            <div class="split-stat-row">
                                <span class="split-stat-label">GA/G</span>
                                <span class="split-stat-value">${game.team_splits.home.ga_pg.toFixed(2)}</span>
                            </div>
                            <div class="split-stat-row">
                                <span class="split-stat-label">Goal Diff</span>
                                <span class="split-stat-value">${game.team_splits.home.goal_diff > 0 ? '+' : ''}${game.team_splits.home.goal_diff.toFixed(2)}</span>
                            </div>
                        </div>
                    </div>
                    <div class="split-card">
                        <div class="split-title">${game.away} on Road</div>
                        <div class="split-stats">
                            <div class="split-stat-row">
                                <span class="split-stat-label">Win %</span>
                                <span class="split-stat-value">${(game.team_splits.away.win_pct * 100).toFixed(1)}%</span>
                            </div>
                            <div class="split-stat-row">
                                <span class="split-stat-label">GF/G</span>
                                <span class="split-stat-value">${game.team_splits.away.gf_pg.toFixed(2)}</span>
                            </div>
                            <div class="split-stat-row">
                                <span class="split-stat-label">GA/G</span>
                                <span class="split-stat-value">${game.team_splits.away.ga_pg.toFixed(2)}</span>
                            </div>
                            <div class="split-stat-row">
                                <span class="split-stat-label">Goal Diff</span>
                                <span class="split-stat-value">${game.team_splits.away.goal_diff > 0 ? '+' : ''}${game.team_splits.away.goal_diff.toFixed(2)}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Injuries
    if (game.injuries && (game.injuries.home.impact_score > 0 || game.injuries.away.impact_score > 0)) {
        html += `
            <div class="details-section">
                <h3>🏥 Injury Impact</h3>
                <div class="injury-list">
                    ${game.injuries.home.impact_score > 0 ? `
                        <div class="injury-item">
                            <span class="injury-team">${game.home}</span>
                            <span class="injury-impact">-${game.injuries.home.impact_score.toFixed(1)} impact</span>
                        </div>
                    ` : ''}
                    ${game.injuries.away.impact_score > 0 ? `
                        <div class="injury-item">
                            <span class="injury-team">${game.away}</span>
                            <span class="injury-impact">-${game.injuries.away.impact_score.toFixed(1)} impact</span>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }
    
    // Advanced Stats
    if (game.advanced_stats && game.advanced_stats.home && game.advanced_stats.away) {
        html += `
            <div class="details-section">
                <h3>📊 Advanced Stats</h3>
                <div class="advanced-stats-grid">
                    <div class="advanced-stat-card">
                        <div class="advanced-stat-label">${game.home} xGF%</div>
                        <div class="advanced-stat-value">${game.advanced_stats.home.xGF_pct.toFixed(1)}%</div>
                    </div>
                    <div class="advanced-stat-card">
                        <div class="advanced-stat-label">${game.away} xGF%</div>
                        <div class="advanced-stat-value">${game.advanced_stats.away.xGF_pct.toFixed(1)}%</div>
                    </div>
                    <div class="advanced-stat-card">
                        <div class="advanced-stat-label">${game.home} Corsi%</div>
                        <div class="advanced-stat-value">${game.advanced_stats.home.corsi_pct.toFixed(1)}%</div>
                    </div>
                    <div class="advanced-stat-card">
                        <div class="advanced-stat-label">${game.away} Corsi%</div>
                        <div class="advanced-stat-value">${game.advanced_stats.away.corsi_pct.toFixed(1)}%</div>
                    </div>
                    <div class="advanced-stat-card">
                        <div class="advanced-stat-label">${game.home} PDO</div>
                        <div class="advanced-stat-value">${game.advanced_stats.home.pdo.toFixed(1)}</div>
                    </div>
                    <div class="advanced-stat-card">
                        <div class="advanced-stat-label">${game.away} PDO</div>
                        <div class="advanced-stat-value">${game.advanced_stats.away.pdo.toFixed(1)}</div>
                    </div>
                </div>
            </div>
        `;
    }
    
    return html;
}

function toggleGameDetails(index) {
    const card = document.querySelectorAll('.game-card')[index];
    card.classList.toggle('expanded');
}

function getGrade(edge) {
    if (edge >= 0.07) return 'A';
    if (edge >= 0.04) return 'B+';
    if (edge >= 0.03) return 'B';
    return 'C+';
}

function getGradeClass(grade) {
    const gradeMap = {
        'A': 'grade-a',
        'B+': 'grade-b-plus',
        'B': 'grade-b',
        'C+': 'grade-c-plus'
    };
    return gradeMap[grade] || 'grade-c-plus';
}

// Load analysis on page load
loadAnalysis();

// Auto-refresh every 5 minutes
setInterval(loadAnalysis, 5 * 60 * 1000);
