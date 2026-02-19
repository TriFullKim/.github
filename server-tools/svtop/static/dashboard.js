/**
 * Server Monitor Dashboard — Client-side logic
 * Handles API data fetching, Chart.js rendering, and auto-refresh.
 */

// ─── State ──────────────────────────────────────────────────────────────────
let currentServer = null;
let currentHours = 1;
let refreshTimer = null;
const REFRESH_INTERVAL = 30_000; // 30 seconds

const charts = {};
const chartColors = {
    cpu: { border: '#6366f1', bg: 'rgba(99, 102, 241, 0.15)' },
    ram: { border: '#10b981', bg: 'rgba(16, 185, 129, 0.15)' },
    gpu: { border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)' },
    disk: { border: '#ef4444', bg: 'rgba(239, 68, 68, 0.15)' },
};

// ─── Chart.js defaults ─────────────────────────────────────────────────────
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = 'rgba(99, 102, 241, 0.08)';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;

// ─── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadServers();
    loadConfig();
    initCharts();
    setupTimeRange();
});

// ─── Verification & Helpers ──────────────────────────────────────────

function isOnline(timestamp) {
    if (!timestamp) return false;
    const ts = new Date(timestamp + 'Z').getTime();
    const now = new Date().getTime();
    const diffMinutes = (now - ts) / 1000 / 60;
    // Consider online if data is younger than 10 minutes (2x default interval)
    return diffMinutes < 10;
}

function renderStatusDot(timestamp) {
    const online = isOnline(timestamp);
    return `<span class="gallery-status-dot ${online ? 'online' : ''}" title="${online ? 'Online' : 'Offline'}"></span>`;
}

async function refreshServer(serverName, btnId) {
    const btn = document.getElementById(btnId);
    if (btn) btn.classList.add('spin');
    
    // Prevent event bubbling if called from card click
    if (event) event.stopPropagation();

    try {
        await api(`/api/collect?server=${encodeURIComponent(serverName)}`, { method: 'POST' });
        // After starting collection, wait a bit then refresh view
        setTimeout(() => {
            if (currentView === 'home') loadOverview();
            else if (currentView === serverName) loadServerDetail(serverName);
            
            if (btn) btn.classList.remove('spin');
        }, 2000); // Wait 2s for collection to likely finish
    } catch (e) {
        console.error("Refresh failed", e);
        if (btn) btn.classList.remove('spin');
    }
}

// ─── API helpers ────────────────────────────────────────────────────────────
async function api(path, options = {}) {
    const res = await fetch(path, options);
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
}

// ─── Load servers into sidebar ──────────────────────────────────────────────
async function loadServers() {
    try {
        const { servers } = await api('/api/servers');
        const list = document.getElementById('serverList');
        
        // Clear all items (Label is now outside this container)
        list.innerHTML = '';

        servers.forEach(name => {
            const item = document.createElement('div');
            item.className = 'nav-item'; // Use common class
            item.dataset.server = name;
            item.innerHTML = `<span class="server-dot"></span><span>${name}</span>`;
            item.addEventListener('click', () => selectServer(name));
            list.appendChild(item);
        });

        // Auto-select first server if none selected
        if (!currentServer && servers.length > 0) {
            // Default to Home view instead of first server
            switchView('home');
        }
    } catch (e) {
        console.error('Failed to load servers:', e);
    }
}

// ─── Load config info ───────────────────────────────────────────────────────
async function loadConfig() {
    try {
        const cfg = await api('/api/config');
        const el = document.getElementById('configInfo');
        el.innerHTML = `
            수집 간격: ${cfg.interval_seconds}초<br>
            보관 기간: ${cfg.retention_days}일<br>
            Notion: ${cfg.notion_enabled ? '✅ 연동중' : '⬜ 비활성'}
        `;
    } catch (e) { /* ignore */ }
}

// ─── Select a server (Legacy wrapper) ───────────────────────────────────────
function selectServer(name) {
    switchView(name);
}

// ─── Load latest snapshot ───────────────────────────────────────────────────
async function loadLatest() {
    if (!currentServer) return;
    try {
        const data = await api(`/api/latest/${encodeURIComponent(currentServer)}`);
        
        try { updateCards(data.metric); } catch(e) { console.error("updateCards failed", e); }
        try { updateProcessTable(data.processes); } catch(e) { console.error("updateProcessTable failed", e); }
        try { updateUserTable(data.users); } catch(e) { console.error("updateUserTable failed", e); }
        try { updateDiskTable(data.disks); } catch(e) { console.error("updateDiskTable failed", e); }
        try { updateHomeTable(data.home_usage); } catch(e) { console.error("updateHomeTable failed", e); }
    } catch (e) {
        console.error('Failed to load latest:', e);
    }
}

// ─── Update metric cards ────────────────────────────────────────────────────
function updateCards(metric) {
    if (!metric) {
        ['Cpu', 'Ram', 'Gpu', 'Disk'].forEach(k => {
            document.getElementById(`val${k}`).textContent = '-';
            document.getElementById(`bar${k}`).style.width = '0%';
        });
        document.getElementById('lastUpdated').textContent = 'No data';
        return;
    }

    // CPU (Threads)
    const load = metric.cpu_load ?? 0;
    const threads = metric.cpu_threads_total ?? 1;
    document.getElementById('valCpu').textContent = `${load.toFixed(2)} / ${threads}`;
    // Bar based on load relative to threads? or just load/threads ratio
    const cpuPct = (load / threads) * 100; 
    document.getElementById('barCpu').style.width = `${Math.min(cpuPct, 100)}%`;

    // RAM (GB)
    const ramPct = metric.ram_total_mb > 0
        ? (metric.ram_used_mb / metric.ram_total_mb * 100)
        : 0;
    const usedGb = (metric.ram_used_mb / 1024).toFixed(1);
    const totalGb = (metric.ram_total_mb / 1024).toFixed(1);
    
    document.getElementById('valRam').textContent = `${usedGb}/${totalGb} GB`;
    document.getElementById('barRam').style.width = `${Math.min(ramPct, 100)}%`;

    // GPU
    if (metric.gpu_util !== null && metric.gpu_util !== undefined) {
        document.getElementById('valGpu').textContent = `${metric.gpu_util.toFixed(1)}%`;
        document.getElementById('barGpu').style.width = `${Math.min(metric.gpu_util, 100)}%`;
    } else {
        document.getElementById('valGpu').textContent = 'N/A';
        document.getElementById('barGpu').style.width = '0%';
    }

    // Disk (Used)
    const diskUsedVal = metric.disk_usage_percent ?? 0;
    const diskUsedBytes = metric.disk_used_bytes ?? 0;
    const diskTotalBytes = metric.disk_total_bytes ?? 0;

    let diskText = `${diskUsedVal.toFixed(1)}%`;
    if (diskTotalBytes > 0) {
        diskText = `${diskUsedVal.toFixed(1)}% <span class="text-muted">(${formatBytes(diskUsedBytes)} / ${formatBytes(diskTotalBytes)})</span>`;
    }

    document.getElementById('valDisk').innerHTML = diskText;
    const liveDot = document.getElementById('liveDot');
    if (liveDot) liveDot.className = `server-dot ${isOnline(metric.timestamp) ? 'online' : ''}`;
    
    // Update Refresh Button
    const btnRef = document.getElementById('btn-ref-detail');
    if (btnRef) {
        btnRef.onclick = () => refreshServer(data.server, 'btn-ref-detail');
    }
    barDisk.className = `bar-fill ${getDiskColor(diskUsedVal)}`;

    // Last updated
    const ts = new Date(metric.timestamp + 'Z');
    const updateEl = document.getElementById('lastUpdated');
    updateEl.textContent = `Last updated: ${ts.toLocaleString('ko-KR')}`;
    
    // Check Online/Offline for content dimming
    const online = isOnline(metric.timestamp);
    const contentIds = ['metricCards', 'processTable', 'diskTable', 'homeTable', 'userTable']; 
    // Actually we should dim the containers: .metric-cards, .charts-grid, .bottom-grid
    const containerIds = ['metricCards', 'chartSection', 'processSection', 'diskSection', 'bottomSection'];
    
    // Helper to get elements easily. We didn't assign IDs to all sections, let's just target by class or add IDs dynamically?
    // Easier: target header siblings.
    // Or just manually target the known containers.
    // In index.html: metricCards (id=metricCards), charts-grid (class), bottom-grid (class)
    
    const grids = document.querySelectorAll('.metric-cards, .charts-grid, .bottom-grid');
    grids.forEach(el => {
        if (online) {
            el.classList.remove('content-offline');
        } else {
            el.classList.add('content-offline');
        }
    });

    if (online) {
        updateEl.classList.remove('stale');
    } else {
        updateEl.classList.add('stale');
        updateEl.textContent += ' (Offline)';
    }
}

// ─── Update process table ───────────────────────────────────────────────────
function updateProcessTable(processes) {
    const tbody = document.getElementById('processBody');
    if (!processes || processes.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No data</td></tr>';
        return;
    }
    tbody.innerHTML = processes.map(p => `
        <tr>
            <td style="font-family:var(--font-mono)">${p.pid}</td>
            <td>${p.user || '-'}</td>
            <td>${p.cpu_percent != null ? p.cpu_percent.toFixed(1) : '-'}%</td>
            <td>${p.mem_percent != null ? p.mem_percent.toFixed(1) : '-'}%</td>
            <td>${escapeHtml(p.command || '-')}</td>
        </tr>
    `).join('');
}

// ─── Update user table ──────────────────────────────────────────────────────
function updateUserTable(users) {
    const tbody = document.getElementById('userBody');
    document.getElementById('userCount').textContent = users?.length ?? 0;

    if (!users || users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted)">No active users</td></tr>';
        return;
    }
    tbody.innerHTML = users.map(u => `
        <tr>
            <td>${escapeHtml(u.username)}</td>
            <td style="font-family:var(--font-mono)">${escapeHtml(u.terminal)}</td>
            <td>${escapeHtml(u.login_time || '-')}</td>
        </tr>
    `).join('');
}

function updateDiskTable(disks) {
    const tbody = document.getElementById('diskTable');
    if (!disks || disks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">No data</td></tr>';
        return;
    }
    
    // Format bytes helper
    const fmt = (b) => {
        if (b > 1024**4) return (b / 1024**4).toFixed(1) + ' TB';
        if (b > 1024**3) return (b / 1024**3).toFixed(1) + ' GB';
        if (b > 1024**2) return (b / 1024**2).toFixed(1) + ' MB';
        return b + ' B';
    };

    tbody.innerHTML = disks.map(d => {
        // The backend `parse_disks` returns "percent" as Free %
        const freePct = (d.free_bytes / d.total_bytes) * 100;
        const usedPct = 100 - freePct;

        return `
            <tr>
                <td style="font-family:var(--font-mono)">${escapeHtml(d.mount_point)}</td>
                <td>${escapeHtml(d.filesystem)}</td>
                <td>${fmt(d.total_bytes)}</td>
                <td>${fmt(d.used_bytes)}</td>
                <td>${fmt(d.free_bytes)}</td>
                <td class="${usedPct > 90 ? 'text-danger' : ''}">${usedPct.toFixed(1)}%</td>
            </tr>
        `;
    }).join('');
}

function updateHomeTable(home) {
    const tbody = document.getElementById('homeTable');
    if (!home || home.length === 0) {
        tbody.innerHTML = '<tr><td colspan="2" style="text-align:center;color:var(--text-muted)">No data (Run collection)</td></tr>';
        return;
    }
    
    const fmt = (b) => {
        if (b > 1024**3) return (b / 1024**3).toFixed(2) + ' GB';
        if (b > 1024**2) return (b / 1024**2).toFixed(1) + ' MB';
        return (b / 1024).toFixed(0) + ' KB';
    };

    tbody.innerHTML = home.map(h => `
        <tr>
            <td>${escapeHtml(h.username)}</td>
            <td>${fmt(h.size_bytes)}</td>
        </tr>
    `).join('');
}

// ─── Init charts ────────────────────────────────────────────────────────────
function initCharts() {
    const commonOpts = (label, color) => ({
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label,
                data: [],
                borderColor: color.border,
                backgroundColor: color.bg,
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                fill: true,
                tension: 0.3,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    borderColor: 'rgba(99, 102, 241, 0.2)',
                    borderWidth: 1,
                    padding: 10,
                    cornerRadius: 8,
                    titleFont: { family: "'Inter', sans-serif", size: 12 },
                    bodyFont: { family: "'JetBrains Mono', monospace", size: 12 },
                },
            },
            scales: {
                x: {
                    type: 'time',
                    time: { tooltipFormat: 'yyyy-MM-dd HH:mm' },
                    grid: { display: false },
                    ticks: { maxTicksLimit: 8 },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(99, 102, 241, 0.06)' },
                },
            },
        },
    });

    charts.cpu = new Chart(document.getElementById('chartCpu'), commonOpts('CPU Load', chartColors.cpu));
    charts.ram = new Chart(document.getElementById('chartRam'), commonOpts('RAM MB', chartColors.ram));
    charts.gpu = new Chart(document.getElementById('chartGpu'), commonOpts('GPU Utilization %', chartColors.gpu));
    charts.disk = new Chart(document.getElementById('chartDisk'), commonOpts('Disk Usage %', chartColors.disk));
}

// ─── Load time series ───────────────────────────────────────────────────────
async function loadTimeSeries() {
    if (!currentServer) return;
    try {
        const { data } = await api(`/api/metrics/${encodeURIComponent(currentServer)}?hours=${currentHours}`);
        const timestamps = data.map(d => new Date(d.timestamp + 'Z'));

        // For charts, we still use cpu_percent (which is now load/threads * 100)
        updateChart(charts.cpu, timestamps, data.map(d => d.cpu_percent));
        updateChart(charts.ram, timestamps, data.map(d => d.ram_used_mb));
        updateChart(charts.gpu, timestamps, data.map(d => d.gpu_util));
        updateChart(charts.disk, timestamps, data.map(d => d.disk_usage_percent));
    } catch (e) {
        console.error('Failed to load time series:', e);
    }
}

function updateChart(chart, labels, data) {
    chart.data.labels = labels;
    chart.data.datasets[0].data = data;
    chart.update('none'); // no animation for performance
}

// ─── Time range buttons ─────────────────────────────────────────────────────
function setupTimeRange() {
    document.querySelectorAll('.btn-range').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.btn-range').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentHours = parseInt(btn.dataset.hours, 10);
            loadTimeSeries();
        });
    });
}

// ─── View Switching ────────────────────────────────────────────────────────
function switchView(viewName) {
    // Hide all dashboards
    document.getElementById('homeDashboard').style.display = 'none';
    document.getElementById('detailDashboard').style.display = 'none';
    document.getElementById('emptyState').style.display = 'none';
    
    // Update Sidebar
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.getElementById('navHome').classList.toggle('active', viewName === 'home');

    if (refreshTimer) clearInterval(refreshTimer);

    if (viewName === 'home') {
        document.getElementById('homeDashboard').style.display = 'block';
        currentServer = null;
        loadHome();
        refreshTimer = setInterval(loadHome, REFRESH_INTERVAL);
    } else {
        document.getElementById('detailDashboard').style.display = 'block';
        currentServer = viewName;
        // Sidebar active state
        const item = document.querySelector(`.nav-item[data-server="${viewName}"]`);
        if (item) item.classList.add('active');
        
        document.getElementById('serverTitle').textContent = viewName;
        loadLatest();
        loadTimeSeries();
        refreshTimer = setInterval(() => {
            loadLatest();
            loadTimeSeries();
        }, REFRESH_INTERVAL);
    }
}

// ─── Load Home Dashboard ───────────────────────────────────────────────────
async function loadHome() {
    try {
        const { overview } = await api('/api/overview');
        renderGallery(overview);
        document.getElementById('homeLastUpdated').textContent = 
            `Last updated: ${new Date().toLocaleString('ko-KR')}`;
    } catch (e) {
        console.error('Failed to load overview:', e);
    }
}

function renderGallery(data) {
    const grid = document.getElementById('galleryGrid');
    grid.innerHTML = '';
    
    data.forEach(server => {
        const card = document.createElement('div');
        card.className = 'gallery-card';
        card.onclick = () => switchView(server.server);
        
        // Calculate Trends
        const gpuTrend = server.current.gpu - server.avg_1h.gpu;
        const diskTrend = server.current.disk - server.avg_1h.disk;
        
        // Use most recent timestamp from history for status check
        const lastTs = server.history.timestamps[server.history.timestamps.length - 1];

        card.innerHTML = `
            <div class="gallery-header">
                <h2>${renderStatusDot(lastTs)} ${server.server}</h2>
                <button class="btn-refresh-sm" id="btn-ref-${server.server}" onclick="refreshServer('${server.server}', 'btn-ref-${server.server}')" title="Refresh">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6"></path><path d="M1 20v-6h6"></path><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
                </button>
            </div>
            
            <div class="gallery-body">
                <div class="gallery-col">
                    <div class="gallery-label">GPU</div>
                    <div class="sparkline-wrapper">
                        <canvas id="spark-gpu-${server.server}"></canvas>
                    </div>
                    <div class="gallery-metric">
                        <span class="gallery-val" style="color:var(--accent-orange)">
                            ${server.current.gpu.toFixed(0)}%
                        </span>
                        ${renderTrend(gpuTrend, 'gpu')}
                    </div>
                </div>
                
                <div class="gallery-divider"></div>

                <div class="gallery-col">
                    <div class="gallery-label">Storage Used</div>
                    <div class="sparkline-wrapper">
                        <canvas id="spark-disk-${server.server}"></canvas>
                    </div>
                    <div class="gallery-metric">
                        <span class="gallery-val" style="color:var(--accent-green)">
                            ${server.current.disk.toFixed(0)}%
                            <span style="font-size:0.5em;color:var(--text-muted);margin-left:4px;">
                                (${formatBytes(server.current.disk_used_bytes)})
                            </span>
                        </span>
                        ${renderTrend(diskTrend, 'disk')}
                    </div>
                </div>
            </div>
        `;
        
        grid.appendChild(card);
        
        // Render Sparklines (Filled Area)
        renderSparkline(`spark-gpu-${server.server}`, server.history.timestamps, server.history.gpu, chartColors.gpu);
        renderSparkline(`spark-disk-${server.server}`, server.history.timestamps, server.history.disk, chartColors.disk);
    });
}


function renderTrend(delta, type) {
    if (Math.abs(delta) < 0.1) return ''; // No significant change
    
    const isUp = delta > 0;
    const arrow = isUp ? '↑' : '↓';
    const val = Math.abs(delta).toFixed(1);
    
    let cls = '';
    if (type === 'gpu') {
        cls = isUp ? 'trend-up' : 'trend-down'; // GPU Up is bad (Red), Down is good (Green)
    } else {
        // Disk Used: Up is bad (Red), Down is good (Green)
        // Re-using same classes since logic is now identical to GPU
        cls = isUp ? 'trend-up' : 'trend-down';
    }
    
    return `<span class="trend-badge ${cls}">${arrow} ${val}%</span>`;
}

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function renderSparkline(id, labels, data, colorObj) {
    const ctx = document.getElementById(id).getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                borderColor: colorObj.border,
                backgroundColor: colorObj.bg, // Fill color
                borderWidth: 2,
                pointRadius: 0,
                fill: true, // Area chart
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: {
                x: { display: false },
                y: { display: false, min: 0, max: 100 }
            },
            layout: { padding: 0 }
        }
    });
}

// ─── Manual collection trigger ──────────────────────────────────────────────
async function triggerCollection() {
    const btn = document.getElementById('collectBtn');
    btn.classList.add('loading');
    btn.disabled = true;

    try {
        await fetch('/api/collect', { method: 'POST' });
        showToast('수집이 시작되었습니다', 'success');
        // Reload after a delay
        setTimeout(() => {
            loadServers();
            if (currentServer) {
                loadLatest();
                loadTimeSeries();
            }
        }, 5000);
    } catch (e) {
        showToast('수집 실행에 실패했습니다', 'error');
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

// ─── Toast ──────────────────────────────────────────────────────────────────
function showToast(msg, type = '') {
    let toast = document.querySelector('.toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.className = 'toast';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.className = `toast ${type}`;
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// ─── Util ───────────────────────────────────────────────────────────────────
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
