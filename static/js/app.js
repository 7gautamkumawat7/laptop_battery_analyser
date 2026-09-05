/**
 * VoltPulse - Battery Health & Analytics Dashboard Client Controller
 * Handles live polling, chart rendering, data filtering, and powercfg reports.
 */

// Global state
let currentBatteryData = null;
let charts = {
    drainTimeline: null,
    dailyActivity: null,
    capacityHistory: null
};

let recentUsageFilter = {
    search: '',
    source: 'all',
    state: 'all',
    page: 1,
    pageSize: 15
};

let livePollTimer = null;

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    initLucide();
    setupEventListeners();

    // Use initial pre-rendered data if available
    if (window.__INITIAL_BATTERY_DATA__ && !window.__INITIAL_BATTERY_DATA__.error) {
        renderDashboard(window.__INITIAL_BATTERY_DATA__);
    } else {
        fetchBatteryData();
    }

    // Start auto polling for live battery percentage
    setupLivePolling();
});

function initLucide() {
    if (window.lucide) {
        window.lucide.createIcons();
    }
}

/**
 * Event Listeners Setup
 */
function setupEventListeners() {
    // Navigation Tabs
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            const targetPaneId = btn.getAttribute('data-tab');
            const targetPane = document.getElementById(targetPaneId);
            if (targetPane) {
                targetPane.classList.add('active');
            }

            // Trigger chart resize on tab switch
            Object.values(charts).forEach(c => {
                if (c) c.resize();
            });
        });
    });

    // Run Fresh Report Button
    const btnGenerate = document.getElementById('btn-generate-report');
    if (btnGenerate) {
        btnGenerate.addEventListener('click', () => {
            generateFreshReport();
        });
    }

    // Export Dropdown Toggle
    const exportBtn = document.getElementById('export-dropdown-btn');
    const exportDropdown = exportBtn ? exportBtn.closest('.dropdown') : null;
    if (exportBtn && exportDropdown) {
        exportBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            exportDropdown.classList.toggle('open');
        });

        document.addEventListener('click', (e) => {
            if (!exportDropdown.contains(e.target)) {
                exportDropdown.classList.remove('open');
            }
        });
    }

    // Auto Refresh Toggle
    const autoToggle = document.getElementById('auto-refresh-toggle');
    if (autoToggle) {
        autoToggle.addEventListener('change', () => {
            if (autoToggle.checked) {
                setupLivePolling();
                showToast('Live telemetry polling active (every 8s)', 'info');
            } else {
                if (livePollTimer) clearInterval(livePollTimer);
                showToast('Live polling paused', 'info');
            }
        });
    }

    // Table Filters
    const searchInput = document.getElementById('usage-search-input');
    const sourceSelect = document.getElementById('source-filter');
    const stateSelect = document.getElementById('state-filter');

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            recentUsageFilter.search = e.target.value.toLowerCase().trim();
            recentUsageFilter.page = 1;
            renderRecentUsageTable();
        });
    }

    if (sourceSelect) {
        sourceSelect.addEventListener('change', (e) => {
            recentUsageFilter.source = e.target.value;
            recentUsageFilter.page = 1;
            renderRecentUsageTable();
        });
    }

    if (stateSelect) {
        stateSelect.addEventListener('change', (e) => {
            recentUsageFilter.state = e.target.value;
            recentUsageFilter.page = 1;
            renderRecentUsageTable();
        });
    }

    // Pagination
    const btnPrev = document.getElementById('btn-prev-page');
    const btnNext = document.getElementById('btn-next-page');

    if (btnPrev) {
        btnPrev.addEventListener('click', () => {
            if (recentUsageFilter.page > 1) {
                recentUsageFilter.page--;
                renderRecentUsageTable();
            }
        });
    }

    if (btnNext) {
        btnNext.addEventListener('click', () => {
            recentUsageFilter.page++;
            renderRecentUsageTable();
        });
    }
}

/**
 * Fetch full report data from Flask API
 */
async function fetchBatteryData(forceRefresh = false) {
    try {
        const url = `/api/battery-data${forceRefresh ? '?refresh=1' : ''}`;
        const res = await fetch(url);
        const json = await res.json();
        if (json.success && json.data) {
            renderDashboard(json.data);
        } else {
            showToast(json.error || 'Failed to fetch battery metrics', 'error');
        }
    } catch (err) {
        console.error('Error fetching battery data:', err);
        showToast('Network error loading battery telemetry', 'error');
    }
}

/**
 * Trigger powercfg /batteryreport execution
 */
async function generateFreshReport() {
    const btn = document.getElementById('btn-generate-report');
    if (btn) {
        btn.classList.add('loading');
        btn.disabled = true;
    }

    showToast('Executing Windows powercfg /batteryreport command...', 'info');
    logTelemetry('Triggered Windows powercfg /batteryreport diagnostic generation...');

    try {
        const res = await fetch('/api/generate-report', { method: 'POST' });
        const json = await res.json();
        if (json.success && json.data) {
            renderDashboard(json.data);
            showToast('Fresh battery report generated & parsed successfully!', 'success');
            logTelemetry('✓ Fresh battery health report generated successfully.');
        } else {
            showToast(json.error || 'Failed to generate battery report', 'error');
            logTelemetry(`✗ powercfg error: ${json.error}`);
        }
    } catch (err) {
        console.error('Generation failed:', err);
        showToast('Failed to execute powercfg report command', 'error');
        logTelemetry(`✗ Network or execution error: ${err.message}`);
    } finally {
        if (btn) {
            btn.classList.remove('loading');
            btn.disabled = false;
        }
    }
}

/**
 * Real-time live status polling
 */
function setupLivePolling() {
    if (livePollTimer) clearInterval(livePollTimer);
    livePollTimer = setInterval(async () => {
        const toggle = document.getElementById('auto-refresh-toggle');
        if (!toggle || !toggle.checked) return;

        try {
            const res = await fetch('/api/live-status');
            const json = await res.json();
            if (json.success && json.live) {
                updateLiveStatusUI(json.live);
            }
        } catch (e) {
            console.warn('Live poll glitch:', e);
        }
    }, 8000);
}

/**
 * Render complete dashboard with parsed report data
 */
function renderDashboard(data) {
    currentBatteryData = data;

    const sys = data.system_info || {};
    const bat = data.battery || {};
    const live = data.live_status || {};
    const verdict = bat.verdict || {};

    // 1. Header & System Badge
    const headerDevice = document.getElementById('header-device-name');
    if (headerDevice) {
        headerDevice.textContent = `${sys.product_name || 'PC'} (${sys.computer_name || 'Host'})`;
    }

    const lastUpdated = document.getElementById('footer-last-updated');
    if (lastUpdated && sys.report_time) {
        lastUpdated.textContent = `Report Timestamp: ${sys.report_time}`;
    }

    // 2. Health Score Card & SVG Circular Gauge
    const healthPctDisplay = document.getElementById('health-pct-display');
    const healthBadge = document.getElementById('health-verdict-badge');
    const healthVerdictTitle = document.getElementById('health-verdict-title');
    const healthVerdictDesc = document.getElementById('health-verdict-desc');
    const gaugeCircle = document.getElementById('gauge-circle');

    const healthVal = bat.health_percent !== null && bat.health_percent !== undefined ? bat.health_percent : 100;
    if (healthPctDisplay) healthPctDisplay.textContent = `${healthVal}%`;

    if (healthBadge) {
        healthBadge.textContent = verdict.status || 'Pristine';
        healthBadge.className = `badge badge-${verdict.badge || 'emerald'}`;
    }

    if (healthVerdictTitle) healthVerdictTitle.textContent = verdict.title || 'Optimal Battery Health';
    if (healthVerdictDesc) healthVerdictDesc.textContent = verdict.description || 'Operating within normal factory thresholds.';

    // Update SVG circle stroke
    if (gaugeCircle) {
        const circumference = 2 * Math.PI * 50; // 314.159
        const strokeColor = verdict.color || '#10b981';
        const offset = circumference - (Math.min(100, Math.max(0, healthVal)) / 100) * circumference;
        gaugeCircle.style.strokeDashoffset = offset;
        gaugeCircle.style.stroke = strokeColor;
    }

    // 3. Live Battery Status Card
    updateLiveStatusUI(live);

    // 4. Capacity Comparison Card
    const fullChargeMwh = document.getElementById('full-charge-mwh');
    const fullChargeWh = document.getElementById('full-charge-wh');
    const designCapMwh = document.getElementById('design-cap-mwh');
    const designCapWh = document.getElementById('design-cap-wh');
    const capacityLostDisplay = document.getElementById('capacity-lost-display');
    const wearBadge = document.getElementById('wear-badge');
    const capacityProgressFill = document.getElementById('capacity-progress-fill');
    const capacityRetentionText = document.getElementById('capacity-retention-text');

    if (fullChargeMwh) fullChargeMwh.textContent = bat.full_charge_capacity_mwh ? `${bat.full_charge_capacity_mwh.toLocaleString()} mWh` : 'N/A';
    if (fullChargeWh) fullChargeWh.textContent = bat.full_charge_capacity_wh ? `(${bat.full_charge_capacity_wh} Wh)` : '';
    if (designCapMwh) designCapMwh.textContent = bat.design_capacity_mwh ? `${bat.design_capacity_mwh.toLocaleString()} mWh` : 'N/A';
    if (designCapWh) designCapWh.textContent = bat.design_capacity_wh ? `(${bat.design_capacity_wh} Wh)` : '';

    if (wearBadge) {
        const wearVal = bat.wear_percent !== null ? bat.wear_percent : 0;
        wearBadge.textContent = `${wearVal}% Wear`;
        wearBadge.className = `badge badge-${wearVal > 20 ? 'amber' : 'cyan'}`;
    }

    if (capacityLostDisplay) {
        const lost = bat.capacity_lost_mwh || 0;
        capacityLostDisplay.textContent = lost > 0 ? `-${lost.toLocaleString()} mWh Lost` : '0 mWh (No Loss)';
    }

    if (capacityProgressFill) {
        const capPct = bat.health_percent !== null ? Math.min(100, bat.health_percent) : 100;
        capacityProgressFill.style.width = `${capPct}%`;
    }

    if (capacityRetentionText) {
        capacityRetentionText.textContent = `${healthVal}% Retained`;
    }

    // 5. Cycle Count Card
    const cycleCountDisplay = document.getElementById('cycle-count-display');
    const cycleWearBadge = document.getElementById('cycle-wear-badge');
    const batteryChemTag = document.getElementById('battery-chem-tag');
    const batterySnTag = document.getElementById('battery-sn-tag');
    const batteryNameDisplay = document.getElementById('battery-name-display');
    const cycleProgressFill = document.getElementById('cycle-progress-fill');
    const cycleProgressText = document.getElementById('cycle-progress-text');

    const cycles = typeof bat.cycle_count === 'number' ? bat.cycle_count : null;
    if (cycleCountDisplay) cycleCountDisplay.textContent = cycles !== null ? cycles : 'N/A';

    if (cycleWearBadge) {
        if (cycles === null) {
            cycleWearBadge.textContent = 'Standard';
            cycleWearBadge.className = 'badge badge-neutral';
        } else if (cycles < 100) {
            cycleWearBadge.textContent = 'Minimal Wear';
            cycleWearBadge.className = 'badge badge-purple';
        } else if (cycles < 300) {
            cycleWearBadge.textContent = 'Moderate Cycles';
            cycleWearBadge.className = 'badge badge-cyan';
        } else {
            cycleWearBadge.textContent = 'High Cycles';
            cycleWearBadge.className = 'badge badge-amber';
        }
    }

    if (batteryChemTag) batteryChemTag.textContent = bat.chemistry || 'Li-Ion';
    if (batterySnTag) batterySnTag.textContent = `SN: ${bat.serial_number || 'N/A'}`;
    if (batteryNameDisplay) batteryNameDisplay.textContent = `${bat.manufacturer || ''} ${bat.name || 'Battery Pack'}`.trim();

    if (cycleProgressFill && cycles !== null) {
        const cycleMax = 500;
        const cycleFillPct = Math.min(100, Math.round((cycles / cycleMax) * 100));
        cycleProgressFill.style.width = `${Math.max(3, cycleFillPct)}%`;
        if (cycleProgressText) cycleProgressText.textContent = `${cycles} / ${cycleMax} Cycles (~${cycleFillPct}%)`;
    }

    // 6. Recent Usage Counter Badge
    const recentCountBadge = document.getElementById('recent-count-badge');
    if (recentCountBadge && data.recent_usage) {
        recentCountBadge.textContent = data.recent_usage.length;
    }

    // 7. Render Sections & Charts
    renderCharts(data);
    renderDailySummaryCards(data.daily_summary || []);
    renderRecentUsageTable();
    renderDrainsTable(data.battery_drains || []);
    renderCapacityHistoryTable(data.capacity_history || []);
    renderEstimatesTable(data.life_estimates || [], data.current_estimate || {});
    renderSystemSpecs(sys, bat);

    initLucide();
}

/**
 * Update real-time live battery status widget and cards
 */
function updateLiveStatusUI(live) {
    if (!live) return;

    const livePillText = document.getElementById('live-pill-text');
    const livePercentDisplay = document.getElementById('live-percent-display');
    const livePowerSource = document.getElementById('live-power-source');
    const liveChargingBadge = document.getElementById('live-charging-badge');
    const liveTimeRemaining = document.getElementById('live-time-remaining');
    const liveChargingState = document.getElementById('live-charging-state');
    const batteryFillBar = document.getElementById('battery-fill-bar');
    const batteryBoltIcon = document.getElementById('battery-bolt-icon');

    const liveGaugePct = document.getElementById('live-gauge-pct');
    const liveGaugeState = document.getElementById('live-gauge-state');
    const liveChipSource = document.getElementById('live-chip-source');
    const liveChipTime = document.getElementById('live-chip-time');
    const liveChipHealth = document.getElementById('live-chip-health');

    const pct = live.percent !== null && live.percent !== undefined ? live.percent : '--';

    if (livePillText) {
        livePillText.textContent = `${pct}% · ${live.charging_state || 'Connected'}`;
    }

    if (livePercentDisplay) livePercentDisplay.textContent = `${pct}%`;
    if (liveGaugePct) liveGaugePct.textContent = `${pct}%`;

    if (livePowerSource) livePowerSource.textContent = live.power_source || 'AC Power';
    if (liveChipSource) liveChipSource.textContent = live.power_plugged ? 'AC Connected' : 'On Battery';

    if (liveChargingBadge) {
        liveChargingBadge.textContent = live.charging_state || 'Online';
        liveChargingBadge.className = `badge badge-${live.status_badge || 'emerald'}`;
    }

    if (liveTimeRemaining) liveTimeRemaining.textContent = live.time_left_formatted || 'On AC Power';
    if (liveChipTime) liveChipTime.textContent = live.time_left_formatted || 'N/A';

    if (liveChargingState) liveChargingState.textContent = live.charging_state || 'Active';
    if (liveGaugeState) liveGaugeState.textContent = `${live.charging_state || 'Online'} (${live.power_source || 'AC'})`;

    if (batteryFillBar && live.percent !== null) {
        batteryFillBar.style.height = `${live.percent}%`;
        if (live.percent < 20) {
            batteryFillBar.style.background = 'linear-gradient(0deg, #ef4444, #f87171)';
            batteryFillBar.style.boxShadow = '0 0 15px rgba(239, 68, 68, 0.5)';
        } else if (live.percent < 50) {
            batteryFillBar.style.background = 'linear-gradient(0deg, #f59e0b, #fbbf24)';
            batteryFillBar.style.boxShadow = '0 0 15px rgba(245, 158, 11, 0.5)';
        } else {
            batteryFillBar.style.background = 'linear-gradient(0deg, #10b981, #34d399)';
            batteryFillBar.style.boxShadow = '0 0 15px rgba(16, 185, 129, 0.5)';
        }
    }

    if (batteryBoltIcon) {
        batteryBoltIcon.style.display = live.power_plugged ? 'block' : 'none';
    }

    if (liveChipHealth && currentBatteryData && currentBatteryData.battery) {
        const h = currentBatteryData.battery.health_percent;
        liveChipHealth.textContent = h !== null ? `${h}%` : '100%';
    }

    // Log to telemetry
    logTelemetry(`[POLL] Battery: ${pct}% | Source: ${live.power_source} | State: ${live.charging_state}`);
}

/**
 * Render Chart.js charts
 */
function renderCharts(data) {
    // 1. Drain Timeline Chart
    const drainCanvas = document.getElementById('drainTimelineChart');
    if (drainCanvas) {
        let labels = [];
        let points = [];

        // Check if high-resolution drain points exist
        if (data.drain_graph_points && data.drain_graph_points.length > 0) {
            data.drain_graph_points.forEach(pt => {
                const timeLabel = (pt.x0 || '').replace('T', ' ').substring(5);
                const pctVal = Math.round((pt.y0 || 0) * 100);
                labels.push(timeLabel);
                points.push(pctVal);
            });
        } else if (data.recent_usage && data.recent_usage.length > 0) {
            // Fallback to recent usage entries
            const reversed = [...data.recent_usage].reverse();
            reversed.forEach(u => {
                if (u.percent !== null) {
                    labels.push(`${u.date ? u.date.substring(5) : ''} ${u.time}`);
                    points.push(u.percent);
                }
            });
        }

        if (charts.drainTimeline) charts.drainTimeline.destroy();

        const ctx = drainCanvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, 'rgba(6, 182, 212, 0.4)');
        gradient.addColorStop(1, 'rgba(6, 182, 212, 0.0)');

        charts.drainTimeline = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels.length > 0 ? labels : ['No recent drain data'],
                datasets: [{
                    label: 'Battery Level (%)',
                    data: points.length > 0 ? points : [100],
                    borderColor: '#06b6d4',
                    borderWidth: 2,
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.3,
                    pointRadius: labels.length > 30 ? 1.5 : 3,
                    pointHoverRadius: 6,
                    pointBackgroundColor: '#06b6d4'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#0f172a',
                        borderColor: 'rgba(6, 182, 212, 0.5)',
                        borderWidth: 1,
                        titleColor: '#fff',
                        bodyColor: '#06b6d4',
                        padding: 10,
                        callbacks: {
                            label: (context) => ` Battery Level: ${context.parsed.y}%`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#64748b', maxRotation: 45, maxTicksLimit: 10, font: { family: 'Inter', size: 10 } }
                    },
                    y: {
                        min: 0,
                        max: 100,
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: {
                            color: '#64748b',
                            font: { family: 'JetBrains Mono', size: 10 },
                            callback: (v) => `${v}%`
                        }
                    }
                }
            }
        });
    }

    // 2. Daily Activity Chart
    const dailyCanvas = document.getElementById('dailyActivityChart');
    if (dailyCanvas && data.daily_summary) {
        const days = data.daily_summary.slice(-7);
        const dayLabels = days.map(d => d.date || 'Unknown');
        const activeCounts = days.map(d => d.active_count || 0);
        const standbyCounts = days.map(d => d.standby_count || 0);

        if (charts.dailyActivity) charts.dailyActivity.destroy();

        charts.dailyActivity = new Chart(dailyCanvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels: dayLabels,
                datasets: [
                    {
                        label: 'Active Sessions',
                        data: activeCounts,
                        backgroundColor: 'rgba(16, 185, 129, 0.8)',
                        borderRadius: 6
                    },
                    {
                        label: 'Standby / Sleep Sessions',
                        data: standbyCounts,
                        backgroundColor: 'rgba(139, 92, 246, 0.8)',
                        borderRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#64748b', font: { size: 10 } }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }
                    }
                }
            }
        });
    }

    // 3. Capacity Degradation History Chart
    const capCanvas = document.getElementById('capacityHistoryChart');
    if (capCanvas && data.capacity_history && data.capacity_history.length > 0) {
        const reversedHistory = [...data.capacity_history].reverse();
        const periods = reversedHistory.map(h => {
            const parts = (h.period || '').split('-');
            return parts.length >= 2 ? parts[0].trim() : h.period;
        });
        const fullCaps = reversedHistory.map(h => h.full_charge_mwh || 0);
        const designCaps = reversedHistory.map(h => h.design_capacity_mwh || 0);

        if (charts.capacityHistory) charts.capacityHistory.destroy();

        charts.capacityHistory = new Chart(capCanvas.getContext('2d'), {
            type: 'line',
            data: {
                labels: periods,
                datasets: [
                    {
                        label: 'Full Charge Capacity (mWh)',
                        data: fullCaps,
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        borderWidth: 2.5,
                        pointRadius: 4,
                        pointHoverRadius: 7,
                        pointBackgroundColor: '#10b981',
                        fill: true,
                        tension: 0.2
                    },
                    {
                        label: 'Design Capacity (mWh)',
                        data: designCaps,
                        borderColor: '#06b6d4',
                        borderDash: [5, 5],
                        borderWidth: 2,
                        pointRadius: 2,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: '#94a3b8', font: { family: 'Inter', size: 12 } }
                    },
                    tooltip: {
                        backgroundColor: '#0f172a',
                        borderColor: 'rgba(16, 185, 129, 0.5)',
                        borderWidth: 1,
                        padding: 10,
                        callbacks: {
                            label: (c) => ` ${c.dataset.label}: ${c.parsed.y.toLocaleString()} mWh`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#64748b', maxRotation: 45, font: { size: 10 } }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: {
                            color: '#64748b',
                            font: { family: 'JetBrains Mono', size: 10 },
                            callback: (v) => `${(v/1000).toFixed(0)}k mWh`
                        }
                    }
                }
            }
        });
    }
}

/**
 * Render daily quick activity breakdown cards
 */
function renderDailySummaryCards(dailySummaries) {
    const container = document.getElementById('daily-summary-cards');
    if (!container) return;

    if (!dailySummaries || dailySummaries.length === 0) {
        container.innerHTML = '<div class="text-muted p-3">No daily history recorded.</div>';
        return;
    }

    const recentDays = dailySummaries.slice(-6).reverse();
    container.innerHTML = recentDays.map(day => `
        <div class="daily-summary-card">
            <div class="daily-card-date">
                <span>${day.date || 'Recent Day'}</span>
                <span class="badge badge-cyan">${day.entries_count} Events</span>
            </div>
            <div class="daily-stats-list">
                <div class="daily-stats-row">
                    <span>Active Usage:</span>
                    <span class="font-mono text-emerald font-bold">${day.active_count} sessions</span>
                </div>
                <div class="daily-stats-row">
                    <span>Standby / Sleep:</span>
                    <span class="font-mono text-purple">${day.standby_count} sessions</span>
                </div>
                <div class="daily-stats-row">
                    <span>Power Source:</span>
                    <span class="font-mono">${day.ac_count} AC · ${day.battery_count} Battery</span>
                </div>
                <div class="daily-stats-row">
                    <span>Charge Range:</span>
                    <span class="font-mono text-highlight">${day.lowest_pct}% - ${day.highest_pct}%</span>
                </div>
            </div>
        </div>
    `).join('');
}

/**
 * Render Recent Usage logs table with filtering & pagination
 */
function renderRecentUsageTable() {
    const tbody = document.getElementById('recent-usage-tbody');
    const paginationInfo = document.getElementById('pagination-info');
    const btnPrev = document.getElementById('btn-prev-page');
    const btnNext = document.getElementById('btn-next-page');

    if (!tbody || !currentBatteryData || !currentBatteryData.recent_usage) return;

    const allRows = currentBatteryData.recent_usage;

    // Filter
    const filtered = allRows.filter(row => {
        // Search
        if (recentUsageFilter.search) {
            const term = recentUsageFilter.search;
            const matchStr = `${row.timestamp} ${row.state} ${row.source} ${row.percent_str}`.toLowerCase();
            if (!matchStr.includes(term)) return false;
        }

        // Source Filter
        if (recentUsageFilter.source !== 'all') {
            if (row.source !== recentUsageFilter.source) return false;
        }

        // State Filter
        if (recentUsageFilter.state !== 'all') {
            if (!row.state.toLowerCase().includes(recentUsageFilter.state.toLowerCase())) return false;
        }

        return true;
    });

    // Pagination
    const total = filtered.length;
    const totalPages = Math.ceil(total / recentUsageFilter.pageSize) || 1;
    if (recentUsageFilter.page > totalPages) recentUsageFilter.page = totalPages;

    const startIdx = (recentUsageFilter.page - 1) * recentUsageFilter.pageSize;
    const paged = filtered.slice(startIdx, startIdx + recentUsageFilter.pageSize);

    if (paginationInfo) {
        paginationInfo.textContent = `Showing ${paged.length > 0 ? startIdx + 1 : 0} to ${startIdx + paged.length} of ${total} entries (Page ${recentUsageFilter.page}/${totalPages})`;
    }

    if (btnPrev) btnPrev.disabled = recentUsageFilter.page <= 1;
    if (btnNext) btnNext.disabled = recentUsageFilter.page >= totalPages;

    if (paged.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-4">No matching usage logs found.</td></tr>`;
        return;
    }

    tbody.innerHTML = paged.map(row => {
        const isBattery = row.source === 'Battery';
        const badgeClass = isBattery ? 'badge-amber' : 'badge-emerald';
        const stateColor = row.state === 'Active' ? 'text-highlight' : 'text-muted';

        return `
            <tr>
                <td class="font-mono">${row.timestamp || `${row.date} ${row.time}`}</td>
                <td class="${stateColor}">${row.state}</td>
                <td><span class="badge ${badgeClass}">${row.source}</span></td>
                <td class="font-mono font-bold">${row.percent_str || (row.percent !== null ? `${row.percent}%` : '-')}</td>
                <td class="font-mono text-muted">${row.mwh_str || '-'}</td>
            </tr>
        `;
    }).join('');
}

/**
 * Render Battery Drains table
 */
function renderDrainsTable(drains) {
    const tbody = document.getElementById('drains-tbody');
    if (!tbody) return;

    if (!drains || drains.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">No active battery drain periods recorded in recent report.</td></tr>`;
        return;
    }

    tbody.innerHTML = drains.map(d => {
        const rate = (d.energy_percent && d.duration_seconds && d.duration_seconds > 0)
            ? `${Math.round((d.energy_percent / (d.duration_seconds / 3600)) * 10) / 10}% / hr`
            : 'N/A';

        return `
            <tr>
                <td class="font-mono">${d.timestamp || `${d.date} ${d.time}`}</td>
                <td>${d.state}</td>
                <td class="font-mono text-highlight">${d.duration} (${d.duration_formatted})</td>
                <td class="font-mono text-rose font-bold">${d.energy_percent_str || '-'}</td>
                <td class="font-mono text-muted">${d.mwh_drain_str || '-'}</td>
                <td class="font-mono text-amber">${rate}</td>
            </tr>
        `;
    }).join('');
}

/**
 * Render Capacity History table
 */
function renderCapacityHistoryTable(history) {
    const tbody = document.getElementById('capacity-history-tbody');
    if (!tbody) return;

    if (!history || history.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-4">No capacity history data available.</td></tr>`;
        return;
    }

    tbody.innerHTML = history.map(h => {
        const diff = (h.design_capacity_mwh && h.full_charge_mwh) ? (h.design_capacity_mwh - h.full_charge_mwh) : 0;
        const lossStr = diff > 0 ? `-${diff.toLocaleString()} mWh` : '0 mWh';
        const healthStr = h.health_percent !== null ? `${h.health_percent}%` : '100%';

        return `
            <tr>
                <td class="font-mono">${h.period}</td>
                <td class="font-mono text-emerald font-bold">${h.full_charge_str || `${h.full_charge_mwh} mWh`}</td>
                <td class="font-mono text-cyan">${h.design_capacity_str || `${h.design_capacity_mwh} mWh`}</td>
                <td class="font-mono"><span class="badge badge-emerald">${healthStr}</span></td>
                <td class="font-mono text-rose">${lossStr}</td>
            </tr>
        `;
    }).join('');
}

/**
 * Render Battery Life Estimates table & banner
 */
function renderEstimatesTable(estimates, currentEstimate) {
    const tbody = document.getElementById('estimates-table-body');
    const estCurrentFull = document.getElementById('est-current-full');
    const estCurrentDesign = document.getElementById('est-current-design');
    const estCurrentDiff = document.getElementById('est-current-diff');

    if (estCurrentFull) estCurrentFull.textContent = currentEstimate.full_active || 'N/A';
    if (estCurrentDesign) estCurrentDesign.textContent = currentEstimate.design_active || 'N/A';

    if (estCurrentDiff && currentEstimate.full_active_secs && currentEstimate.design_active_secs) {
        const diffSecs = currentEstimate.design_active_secs - currentEstimate.full_active_secs;
        const diffMins = Math.round(diffSecs / 60);
        estCurrentDiff.textContent = diffMins > 0 ? `-${diffMins} min runtime wear` : 'Optimal (0 min wear)';
    }

    if (!tbody) return;

    if (!estimates || estimates.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-4">No life estimates available.</td></tr>`;
        return;
    }

    tbody.innerHTML = estimates.map(e => `
        <tr>
            <td class="font-mono">${e.period}</td>
            <td class="font-mono text-emerald font-bold">${e.full_active || '-'}</td>
            <td class="font-mono text-muted">${e.full_standby || '-'}</td>
            <td class="font-mono text-cyan font-bold">${e.design_active || '-'}</td>
            <td class="font-mono text-muted">${e.design_standby || '-'}</td>
        </tr>
    `).join('');
}

/**
 * Render System & Battery Hardware specs
 */
function renderSystemSpecs(sys, bat) {
    const setElem = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val || 'N/A';
    };

    setElem('spec-comp-name', sys.computer_name);
    setElem('spec-product-name', sys.product_name);
    setElem('spec-bios', sys.bios);
    setElem('spec-os', sys.os_build);
    setElem('spec-role', sys.platform_role);
    setElem('spec-standby', sys.connected_standby);
    setElem('spec-report-time', sys.report_time);

    setElem('spec-bat-name', bat.name);
    setElem('spec-bat-mfg', bat.manufacturer);
    setElem('spec-bat-sn', bat.serial_number);
    setElem('spec-bat-chem', bat.chemistry);
    setElem('spec-bat-design', bat.design_capacity_mwh ? `${bat.design_capacity_mwh.toLocaleString()} mWh (${bat.design_capacity_wh} Wh)` : 'N/A');
    setElem('spec-bat-full', bat.full_charge_capacity_mwh ? `${bat.full_charge_capacity_mwh.toLocaleString()} mWh (${bat.full_charge_capacity_wh} Wh)` : 'N/A');
    setElem('spec-bat-cycles', bat.cycle_count !== null ? bat.cycle_count : 'N/A');
}

/**
 * Append message to live telemetry terminal
 */
function logTelemetry(msg) {
    const term = document.getElementById('telemetry-terminal');
    if (!term) return;

    const timeStr = new Date().toTimeString().split(' ')[0];
    const line = document.createElement('div');
    line.className = 'term-line';
    line.textContent = `[${timeStr}] ${msg}`;
    term.appendChild(line);

    // Keep max 50 lines
    while (term.children.length > 50) {
        term.removeChild(term.firstChild);
    }

    term.scrollTop = term.scrollHeight;
}

/**
 * Display toast notification
 */
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i data-lucide="${type === 'success' ? 'check-circle' : type === 'error' ? 'alert-circle' : 'info'}"></i>
        <span>${message}</span>
    `;

    container.appendChild(toast);
    initLucide();

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        toast.style.transition = '0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
