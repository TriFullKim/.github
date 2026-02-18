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

// ─── API helpers ────────────────────────────────────────────────────────────
async function api(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`API ${res.status}`);
    return res.json();
}

// ─── Load servers into sidebar ──────────────────────────────────────────────
async function loadServers() {
    try {
        const { servers } = await api('/api/servers');
        const list = document.getElementById('serverList');
        const label = list.querySelector('.server-list-label');
        // Clear existing items (keep label)
        list.querySelectorAll('.server-item').forEach(el => el.remove());

        servers.forEach(name => {
            const item = document.createElement('div');
            item.className = 'server-item';
            item.dataset.server = name;
            item.innerHTML = `<span class="server-dot"></span><span>${name}</span>`;
            item.addEventListener('click', () => selectServer(name));
            list.appendChild(item);
        });

        // Auto-select first server if none selected
        if (!currentServer && servers.length > 0) {
            selectServer(servers[0]);
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

// ─── Select a server ────────────────────────────────────────────────────────
function selectServer(name) {
    currentServer = name;

    // Update sidebar active state
    document.querySelectorAll('.server-item').forEach(el => {
        el.classList.toggle('active', el.dataset.server === name);
    });

    // Show dashboard, hide empty state
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('dashboard').style.display = 'block';
    document.getElementById('serverTitle').textContent = name;

    // Load data
    loadLatest();
    loadTimeSeries();

    // Setup auto-refresh
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
        loadLatest();
        loadTimeSeries();
    }, REFRESH_INTERVAL);
}

// ─── Load latest snapshot ───────────────────────────────────────────────────
async function loadLatest() {
    if (!currentServer) return;
    try {
        const data = await api(`/api/latest/${encodeURIComponent(currentServer)}`);
        updateCards(data.metric);
        updateProcessTable(data.processes);
        updateUserTable(data.users);
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

    // CPU
    const cpu = metric.cpu_percent ?? 0;
    document.getElementById('valCpu').textContent = `${cpu.toFixed(1)}%`;
    document.getElementById('barCpu').style.width = `${Math.min(cpu, 100)}%`;

    // RAM
    const ramPct = metric.ram_total_mb > 0
        ? (metric.ram_used_mb / metric.ram_total_mb * 100)
        : 0;
    document.getElementById('valRam').textContent =
        `${Math.round(metric.ram_used_mb)}/${Math.round(metric.ram_total_mb)} MB`;
    document.getElementById('barRam').style.width = `${Math.min(ramPct, 100)}%`;

    // GPU
    if (metric.gpu_util !== null && metric.gpu_util !== undefined) {
        document.getElementById('valGpu').textContent = `${metric.gpu_util.toFixed(1)}%`;
        document.getElementById('barGpu').style.width = `${Math.min(metric.gpu_util, 100)}%`;
    } else {
        document.getElementById('valGpu').textContent = 'N/A';
        document.getElementById('barGpu').style.width = '0%';
    }

    // Disk
    const disk = metric.disk_usage_percent ?? 0;
    document.getElementById('valDisk').textContent = `${disk.toFixed(1)}%`;
    document.getElementById('barDisk').style.width = `${Math.min(disk, 100)}%`;

    // Last updated
    const ts = new Date(metric.timestamp + 'Z');
    document.getElementById('lastUpdated').textContent =
        `Last updated: ${ts.toLocaleString('ko-KR')}`;
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
            <td>${p.cpu_percent?.toFixed(1) ?? '-'}%</td>
            <td>${p.mem_percent?.toFixed(1) ?? '-'}%</td>
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

    charts.cpu = new Chart(document.getElementById('chartCpu'), commonOpts('CPU %', chartColors.cpu));
    charts.ram = new Chart(document.getElementById('chartRam'), commonOpts('RAM MB', chartColors.ram));
    charts.gpu = new Chart(document.getElementById('chartGpu'), commonOpts('GPU %', chartColors.gpu));
    charts.disk = new Chart(document.getElementById('chartDisk'), commonOpts('Disk %', chartColors.disk));
}

// ─── Load time series ───────────────────────────────────────────────────────
async function loadTimeSeries() {
    if (!currentServer) return;
    try {
        const { data } = await api(`/api/metrics/${encodeURIComponent(currentServer)}?hours=${currentHours}`);
        const timestamps = data.map(d => new Date(d.timestamp + 'Z'));

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
