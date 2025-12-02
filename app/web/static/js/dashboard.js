/* global document, fetch, Chart, window */

// ============================================================================
// State Management
// ============================================================================
const state = {
  data: [],
  filtered: [],
  range: '24h',
  slider: 100,
  isLoading: false,
  lastUpdate: null,
};

const charts = {
  download: null,
  upload: null,
  ping: null,
  jitter: null,
};

// ============================================================================
// Chart.js Global Configuration
// ============================================================================
Chart.defaults.color = 'rgba(226, 232, 240, 0.8)';
Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.1)';
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";

// ============================================================================
// Utility Functions
// ============================================================================
function formatMbps(value) {
  if (value === null || value === undefined) return '—';
  return value.toFixed(2);
}

function formatMs(value) {
  if (value === null || value === undefined) return '—';
  return value.toFixed(1);
}

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined) return '—';
  return value.toFixed(decimals);
}

function rangeToMs(range) {
  const map = {
    '24h': 24 * 60 * 60 * 1000,
    '7d': 7 * 24 * 60 * 60 * 1000,
    '30d': 30 * 24 * 60 * 60 * 1000,
  };
  return map[range] || map['7d'];
}

// ============================================================================
// Toast Notifications
// ============================================================================
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  const icons = {
    success: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
    error: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
    warning: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    info: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
  };
  
  toast.innerHTML = `
    <div class="toast-icon">${icons[type] || icons.info}</div>
    <div class="toast-content">
      <span class="toast-message">${message}</span>
    </div>
    <button class="toast-close" onclick="this.parentElement.remove()">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>
  `;
  
  container.appendChild(toast);
  
  // Animate in
  requestAnimationFrame(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateX(0)';
  });
  
  // Auto remove
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ============================================================================
// Count-Up Animation
// ============================================================================
function animateValue(element, start, end, duration = 800) {
  if (start === end) return;
  
  const startTime = performance.now();
  const isDecimal = end.toString().includes('.') || (typeof end === 'number' && end % 1 !== 0);
  const decimals = isDecimal ? (end < 10 ? 2 : 1) : 0;
  
  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    
    // Easing function (ease-out-expo)
    const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
    const current = start + (end - start) * eased;
    
    element.textContent = current.toFixed(decimals);
    
    if (progress < 1) {
      requestAnimationFrame(update);
    }
  }
  
  requestAnimationFrame(update);
}

// ============================================================================
// Sparkline Mini Charts
// ============================================================================
function drawSparkline(containerId, data, color = '#22d3ee') {
  const container = document.getElementById(containerId);
  if (!container || !data || data.length < 2) {
    if (container) container.innerHTML = '';
    return;
  }
  
  const width = container.offsetWidth || 100;
  const height = container.offsetHeight || 30;
  
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  
  const points = data.map((value, index) => {
    const x = (index / (data.length - 1)) * width;
    const y = height - ((value - min) / range) * height;
    return `${x},${y}`;
  }).join(' ');
  
  container.innerHTML = `
    <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
      <defs>
        <linearGradient id="sparkGrad-${containerId}" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" style="stop-color:${color};stop-opacity:0.3"/>
          <stop offset="100%" style="stop-color:${color};stop-opacity:0"/>
        </linearGradient>
      </defs>
      <polyline
        points="${points}"
        fill="none"
        stroke="${color}"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <polygon
        points="0,${height} ${points} ${width},${height}"
        fill="url(#sparkGrad-${containerId})"
      />
    </svg>
  `;
}

// ============================================================================
// Delta Display with Arrow Icons
// ============================================================================
function updateDelta(elementId, value, unit, inverse = false) {
  const element = document.getElementById(elementId);
  if (!element) return;
  
  if (value === null || value === undefined) {
    element.className = 'metric-delta neutral';
    element.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/></svg>
      —
    `;
    return;
  }
  
  const sign = value >= 0 ? '+' : '';
  const isPositive = inverse ? value < 0 : value > 0;
  const isNegative = inverse ? value > 0 : value < 0;
  
  let className = 'metric-delta neutral';
  let arrowSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
  
  if (isPositive) {
    className = 'metric-delta positive';
    arrowSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"/></svg>`;
  } else if (isNegative) {
    className = 'metric-delta negative';
    arrowSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>`;
  }
  
  element.className = className;
  element.innerHTML = `${arrowSvg} ${sign}${Math.abs(value).toFixed(2)} ${unit}`;
}

// ============================================================================
// Progress Bar Updates
// ============================================================================
function updateProgressBar(elementId, value, maxValue) {
  const element = document.getElementById(elementId);
  if (!element) return;
  
  const percentage = Math.min(100, Math.max(0, (value / maxValue) * 100));
  element.style.width = `${percentage}%`;
}

// ============================================================================
// Data Loading & Refresh
// ============================================================================
async function refreshSummary() {
  try {
    const response = await fetch('/api/summary/latest');
    const payload = await response.json();
    
    if (!payload.latest) return;
    
    const data = payload.latest;
    
    // Update values with animation
    const downloadEl = document.getElementById('download-value');
    const uploadEl = document.getElementById('upload-value');
    const pingEl = document.getElementById('ping-value');
    const jitterEl = document.getElementById('jitter-value');
    
    const currentDownload = parseFloat(downloadEl.textContent) || 0;
    const currentUpload = parseFloat(uploadEl.textContent) || 0;
    const currentPing = parseFloat(pingEl.textContent) || 0;
    const currentJitter = parseFloat(jitterEl.textContent) || 0;
    
    animateValue(downloadEl, currentDownload, data.download || 0);
    animateValue(uploadEl, currentUpload, data.upload || 0);
    animateValue(pingEl, currentPing, data.ping_idle || 0);
    animateValue(jitterEl, currentJitter, data.jitter || 0);
    
    // Update additional metrics if available
    const pingDownEl = document.getElementById('ping-down-value');
    const pingUpEl = document.getElementById('ping-up-value');
    const dlLatencyEl = document.getElementById('dl-latency-value');
    const ulLatencyEl = document.getElementById('ul-latency-value');
    
    if (pingDownEl) {
      const current = parseFloat(pingDownEl.textContent) || 0;
      animateValue(pingDownEl, current, data.ping_under_download || 0);
    }
    if (pingUpEl) {
      const current = parseFloat(pingUpEl.textContent) || 0;
      animateValue(pingUpEl, current, data.ping_under_upload || 0);
    }
    if (dlLatencyEl) {
      const current = parseFloat(dlLatencyEl.textContent) || 0;
      animateValue(dlLatencyEl, current, data.download_latency || 0);
    }
    if (ulLatencyEl) {
      const current = parseFloat(ulLatencyEl.textContent) || 0;
      animateValue(ulLatencyEl, current, data.upload_latency || 0);
    }
    
    // Update progress bars (assuming max values)
    updateProgressBar('download-progress', data.download || 0, 1000);
    updateProgressBar('upload-progress', data.upload || 0, 500);
    updateProgressBar('ping-progress', data.ping_idle || 0, 100);
    updateProgressBar('jitter-progress', data.jitter || 0, 50);
    updateProgressBar('ping-down-progress', data.ping_under_download || 0, 200);
    updateProgressBar('ping-up-progress', data.ping_under_upload || 0, 200);
    updateProgressBar('dl-latency-progress', data.download_latency || 0, 100);
    updateProgressBar('ul-latency-progress', data.upload_latency || 0, 100);
    
    // Update deltas
    if (payload.delta) {
      updateDelta('download-delta', payload.delta.download, 'Mbps');
      updateDelta('upload-delta', payload.delta.upload, 'Mbps');
      updateDelta('ping-delta', payload.delta.ping_idle, 'ms', true);
      updateDelta('jitter-delta', payload.delta.jitter, 'ms', true);
      updateDelta('ping-down-delta', payload.delta.ping_under_download, 'ms', true);
      updateDelta('ping-up-delta', payload.delta.ping_under_upload, 'ms', true);
      updateDelta('dl-latency-delta', payload.delta.download_latency, 'ms', true);
      updateDelta('ul-latency-delta', payload.delta.upload_latency, 'ms', true);
    }
    
    state.lastUpdate = new Date();
    
  } catch (error) {
    console.error('Error refreshing summary:', error);
    showToast('Failed to refresh summary', 'error');
  }
}

async function loadMeasurements() {
  state.isLoading = true;
  
  try {
    const params = new URLSearchParams();
    const startInput = document.getElementById('range-start');
    const endInput = document.getElementById('range-end');
    
    if (state.range === 'custom') {
      if (startInput && startInput.value) {
        params.append('start', new Date(startInput.value).toISOString());
      }
      if (endInput && endInput.value) {
        params.append('end', new Date(endInput.value).toISOString());
      }
    } else {
      const windowMs = rangeToMs(state.range);
      const startDate = new Date(Date.now() - windowMs);
      params.append('start', startDate.toISOString());
    }
    params.append('limit', '5000');
    
    const response = await fetch(`/api/measurements?${params.toString()}`);
    state.data = await response.json();
    applyFilters();
    
  } catch (error) {
    console.error('Error loading measurements:', error);
    showToast('Failed to load measurements', 'error');
  } finally {
    state.isLoading = false;
  }
}

function applyFilters() {
  if (!state.data.length) {
    state.filtered = [];
    render();
    return;
  }
  
  const sliderFraction = state.slider / 100;
  const times = state.data.map((item) => new Date(item.timestamp).getTime());
  const min = Math.min(...times);
  const max = Math.max(...times);
  const cutoff = min + (max - min) * sliderFraction;
  
  state.filtered = state.data.filter((item) => new Date(item.timestamp).getTime() <= cutoff);
  render();
}

// ============================================================================
// Rendering
// ============================================================================
function render() {
  updateTable();
  updateCharts();
  updateSparklines();
}

function updateTable() {
  const tbody = document.getElementById('measurement-table');
  if (!tbody) return;
  
  // Build new content
  const rows = state.filtered.slice().reverse().slice(0, 100).map((item) => {
    return `
      <tr>
        <td>${new Date(item.timestamp).toLocaleString()}</td>
        <td><span class="type-badge ${item.measurement_type}">${item.measurement_type}</span></td>
        <td>${item.server || '—'}</td>
        <td>${formatNumber(item.download)} Mbps</td>
        <td>${formatNumber(item.upload)} Mbps</td>
        <td>${formatNumber(item.ping_idle)} ms</td>
        <td>${formatNumber(item.jitter)} ms</td>
        <td>${formatNumber(item.ping_under_download)} ms</td>
        <td>${formatNumber(item.ping_under_upload)} ms</td>
      </tr>
    `;
  }).join('');
  
  tbody.innerHTML = rows;
}

function updateSparklines() {
  if (state.filtered.length < 2) return;
  
  const recentData = state.filtered.slice(-20);
  
  drawSparkline('download-sparkline', recentData.map(d => d.download || 0), '#22d3ee');
  drawSparkline('upload-sparkline', recentData.map(d => d.upload || 0), '#3b82f6');
  drawSparkline('ping-sparkline', recentData.map(d => d.ping_idle || 0), '#f97316');
  drawSparkline('jitter-sparkline', recentData.map(d => d.jitter || 0), '#a855f7');
  drawSparkline('ping-down-sparkline', recentData.map(d => d.ping_under_download || 0), '#fb923c');
  drawSparkline('ping-up-sparkline', recentData.map(d => d.ping_under_upload || 0), '#facc15');
  drawSparkline('dl-latency-sparkline', recentData.map(d => d.download_latency || 0), '#22d3ee');
  drawSparkline('ul-latency-sparkline', recentData.map(d => d.upload_latency || 0), '#3b82f6');
}

function updateCharts() {
  const labels = state.filtered.map((item) => new Date(item.timestamp));
  
  const downloadData = state.filtered.map((item) => item.download);
  const uploadData = state.filtered.map((item) => item.upload);
  const pingIdle = state.filtered.map((item) => item.ping_idle);
  const pingDown = state.filtered.map((item) => item.ping_under_download);
  const pingUp = state.filtered.map((item) => item.ping_under_upload);
  const jitter = state.filtered.map((item) => item.jitter);
  
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
      duration: 800,
      easing: 'easeOutQuart',
    },
    interaction: {
      intersect: false,
      mode: 'index',
    },
    plugins: {
      legend: {
        display: true,
        position: 'top',
        labels: {
          usePointStyle: true,
          padding: 20,
          font: {
            size: 12,
            weight: '500',
          },
        },
      },
      tooltip: {
        backgroundColor: 'rgba(15, 23, 42, 0.9)',
        titleFont: { size: 14, weight: '600' },
        bodyFont: { size: 13 },
        padding: 12,
        borderColor: 'rgba(255, 255, 255, 0.1)',
        borderWidth: 1,
        cornerRadius: 8,
        displayColors: true,
        usePointStyle: true,
      },
    },
    scales: {
      x: {
        type: 'time',
        time: { unit: 'hour' },
        grid: {
          color: 'rgba(255, 255, 255, 0.05)',
          drawBorder: false,
        },
        ticks: {
          maxRotation: 0,
          font: { size: 11 },
        },
      },
      y: {
        beginAtZero: true,
        grid: {
          color: 'rgba(255, 255, 255, 0.05)',
          drawBorder: false,
        },
        ticks: {
          font: { size: 11 },
        },
      },
    },
    elements: {
      point: {
        radius: 3,
        hoverRadius: 6,
        borderWidth: 2,
        backgroundColor: 'rgba(15, 23, 42, 0.8)',
      },
      line: {
        tension: 0.4,
        borderWidth: 2.5,
      },
    },
  };
  
  // Download Chart
  const downloadCtx = document.getElementById('download-chart');
  if (downloadCtx) {
    charts.download = renderLineChart(
      charts.download,
      downloadCtx.getContext('2d'),
      labels,
      [{
        label: 'Download Mbps',
        data: downloadData,
        borderColor: '#22d3ee',
        backgroundColor: 'rgba(34, 211, 238, 0.1)',
        fill: true,
      }],
      chartOptions
    );
  }
  
  // Upload Chart
  const uploadCtx = document.getElementById('upload-chart');
  if (uploadCtx) {
    charts.upload = renderLineChart(
      charts.upload,
      uploadCtx.getContext('2d'),
      labels,
      [{
        label: 'Upload Mbps',
        data: uploadData,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
      }],
      chartOptions
    );
  }
  
  // Ping Chart
  const pingCtx = document.getElementById('ping-chart');
  if (pingCtx) {
    charts.ping = renderLineChart(
      charts.ping,
      pingCtx.getContext('2d'),
      labels,
      [
        { label: 'Idle Ping', data: pingIdle, borderColor: '#f97316', backgroundColor: 'rgba(249, 115, 22, 0.1)' },
        { label: 'Download Ping', data: pingDown, borderColor: '#fb923c', backgroundColor: 'rgba(251, 146, 60, 0.1)' },
        { label: 'Upload Ping', data: pingUp, borderColor: '#facc15', backgroundColor: 'rgba(250, 204, 21, 0.1)' },
      ],
      chartOptions
    );
  }
  
  // Jitter Chart
  const jitterCtx = document.getElementById('jitter-chart');
  if (jitterCtx) {
    charts.jitter = renderLineChart(
      charts.jitter,
      jitterCtx.getContext('2d'),
      labels,
      [{
        label: 'Jitter',
        data: jitter,
        borderColor: '#a855f7',
        backgroundColor: 'rgba(168, 85, 247, 0.1)',
        fill: true,
      }],
      chartOptions
    );
  }
}

function renderLineChart(chart, ctx, labels, datasets, options) {
  if (chart) {
    chart.data.labels = labels;
    chart.data.datasets = datasets;
    chart.update('active');
    return chart;
  }
  
  return new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options,
  });
}

// ============================================================================
// Event Handlers
// ============================================================================
async function triggerManual(endpoint) {
  showToast(`Running ${endpoint} test...`, 'info');
  
  try {
    const response = await fetch(`/api/manual/${endpoint}`, { method: 'POST' });
    
    if (response.ok) {
      showToast(`${endpoint} test queued successfully!`, 'success');
      
      // Poll for results
      setTimeout(async () => {
        await refreshSummary();
        await loadMeasurements();
        showToast('Results updated!', 'success');
      }, 5000);
    } else {
      throw new Error('Request failed');
    }
  } catch (error) {
    showToast(`Failed to trigger ${endpoint} test`, 'error');
  }
}

function exportCsv() {
  const params = new URLSearchParams();
  
  if (state.filtered.length) {
    params.append('start', state.filtered[0].timestamp);
    params.append('end', state.filtered[state.filtered.length - 1].timestamp);
  }
  
  window.location.href = `/api/export/csv?${params.toString()}`;
  showToast('Downloading CSV export...', 'success');
}

function attachEvents() {
  // Filter buttons
  const filterBtns = document.querySelectorAll('.filter-btn');
  filterBtns.forEach((button) => {
    button.addEventListener('click', () => {
      filterBtns.forEach(btn => btn.classList.remove('active'));
      button.classList.add('active');
      state.range = button.dataset.range;
      loadMeasurements();
    });
  });
  
  // Time slider
  const slider = document.getElementById('time-slider');
  const sliderValue = document.getElementById('slider-value');
  if (slider) {
    slider.addEventListener('input', () => {
      state.slider = Number(slider.value);
      if (sliderValue) sliderValue.textContent = `${state.slider}%`;
      applyFilters();
    });
  }
  
  // Action buttons
  const speedtestBtn = document.getElementById('trigger-speedtest');
  const bufferbloatBtn = document.getElementById('trigger-bufferbloat');
  const exportBtn = document.getElementById('export-csv');
  
  if (speedtestBtn) {
    speedtestBtn.addEventListener('click', () => triggerManual('speedtest'));
  }
  if (bufferbloatBtn) {
    bufferbloatBtn.addEventListener('click', () => triggerManual('bufferbloat'));
  }
  if (exportBtn) {
    exportBtn.addEventListener('click', exportCsv);
  }
  
  // Date inputs
  const startInput = document.getElementById('range-start');
  const endInput = document.getElementById('range-end');
  
  [startInput, endInput].forEach((input) => {
    if (input) {
      input.addEventListener('change', () => {
        document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelector('.filter-btn[data-range="custom"]')?.classList.add('active');
        state.range = 'custom';
        loadMeasurements();
      });
    }
  });
}

// ============================================================================
// Scheduler Configuration Modal
// ============================================================================
function initSchedulerModal() {
  const modal = document.getElementById('scheduler-modal');
  const openBtn = document.getElementById('open-scheduler-config');
  const closeBtn = document.getElementById('close-scheduler-modal');
  const cancelBtn = document.getElementById('cancel-scheduler');
  const saveBtn = document.getElementById('save-scheduler');
  
  // Mode switching
  const modeBtns = document.querySelectorAll('.mode-btn');
  const panels = document.querySelectorAll('.scheduler-panel');
  
  modeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.mode;
      
      modeBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      
      panels.forEach(p => p.classList.remove('active'));
      document.getElementById(`${mode}-panel`).classList.add('active');
    });
  });
  
  // Simple mode - sync slider and number input
  const intervalSlider = document.getElementById('interval-minutes');
  const intervalValue = document.getElementById('interval-minutes-value');
  
  if (intervalSlider && intervalValue) {
    intervalSlider.addEventListener('input', () => {
      intervalValue.value = intervalSlider.value;
    });
    
    intervalValue.addEventListener('input', () => {
      intervalSlider.value = intervalValue.value;
    });
  }
  
  // Weekly mode - sync slider and number input
  const weeklySlider = document.getElementById('weekly-interval');
  const weeklyValue = document.getElementById('weekly-interval-value');
  
  if (weeklySlider && weeklyValue) {
    weeklySlider.addEventListener('input', () => {
      weeklyValue.value = weeklySlider.value;
    });
    
    weeklyValue.addEventListener('input', () => {
      weeklySlider.value = weeklyValue.value;
    });
  }
  
  // Advanced mode - disable inputs when day is unchecked
  document.querySelectorAll('.day-toggle').forEach(toggle => {
    toggle.addEventListener('change', () => {
      const daySchedule = toggle.closest('.day-schedule');
      const inputs = daySchedule.querySelectorAll('.day-config input');
      inputs.forEach(input => {
        input.disabled = !toggle.checked;
      });
    });
    
    // Initial state
    const daySchedule = toggle.closest('.day-schedule');
    const inputs = daySchedule.querySelectorAll('.day-config input');
    inputs.forEach(input => {
      input.disabled = !toggle.checked;
    });
  });
  
  // Open modal
  openBtn?.addEventListener('click', () => {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  });
  
  // Close modal
  const closeModal = () => {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  };
  
  closeBtn?.addEventListener('click', closeModal);
  cancelBtn?.addEventListener('click', closeModal);
  
  // Close on backdrop click
  modal?.addEventListener('click', (e) => {
    if (e.target === modal) {
      closeModal();
    }
  });
  
  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.classList.contains('active')) {
      closeModal();
    }
  });
  
  // Save configuration
  saveBtn?.addEventListener('click', async () => {
    const activeMode = document.querySelector('.mode-btn.active')?.dataset.mode || 'simple';
    
    let config = { mode: activeMode };
    
    if (activeMode === 'simple') {
      config.enabled = document.getElementById('scheduler-enabled').checked;
      config.interval = parseInt(intervalValue.value);
    } else if (activeMode === 'weekly') {
      const selectedDays = [];
      document.querySelectorAll('.weekday-selector input[type="checkbox"]:checked').forEach(cb => {
        selectedDays.push(parseInt(cb.value));
      });
      
      config.days = selectedDays;
      config.startTime = document.getElementById('start-time').value;
      config.endTime = document.getElementById('end-time').value;
      config.interval = parseInt(weeklyValue.value);
    } else if (activeMode === 'advanced') {
      config.schedule = {};
      
      document.querySelectorAll('.day-toggle:checked').forEach(toggle => {
        const day = toggle.dataset.day;
        const daySchedule = toggle.closest('.day-schedule');
        const inputs = daySchedule.querySelectorAll('.day-config input');
        
        config.schedule[day] = {
          startTime: inputs[0].value,
          endTime: inputs[1].value,
          interval: parseInt(inputs[2].value)
        };
      });
    }
    
    // Save to localStorage for now (in production, send to backend)
    localStorage.setItem('schedulerConfig', JSON.stringify(config));
    
    showToast(`Scheduler configured in ${activeMode} mode!`, 'success');
    closeModal();
    
    // Update status pill
    updateSchedulerStatus(config);
  });
}

function updateSchedulerStatus(config) {
  const statusPill = document.querySelector('.status-pill span:last-child');
  if (!statusPill) return;
  
  if (config.mode === 'simple') {
    const status = config.enabled ? 'Active' : 'Inactive';
    statusPill.textContent = `Scheduler: ${status} · ${config.interval}min interval`;
  } else if (config.mode === 'weekly') {
    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const days = config.days.map(d => dayNames[d]).join(', ');
    statusPill.textContent = `Scheduler: Weekly · ${days} · ${config.startTime}-${config.endTime} · ${config.interval}min`;
  } else if (config.mode === 'advanced') {
    const activeDays = Object.keys(config.schedule).length;
    statusPill.textContent = `Scheduler: Advanced · ${activeDays} days configured`;
  }
}

// Load saved scheduler config on startup
function loadSchedulerConfig() {
  try {
    const saved = localStorage.getItem('schedulerConfig');
    if (saved) {
      const config = JSON.parse(saved);
      updateSchedulerStatus(config);
    }
  } catch (error) {
    console.error('Failed to load scheduler config:', error);
  }
}

// ============================================================================
// Initialization
// ============================================================================
async function init() {
  attachEvents();
  initSchedulerModal();
  loadSchedulerConfig();
  
  try {
    await refreshSummary();
    await loadMeasurements();
    showToast('Dashboard loaded successfully!', 'success', 2000);
  } catch (error) {
    console.error('Initialization error:', error);
    showToast('Some data failed to load', 'warning');
  }
  
  // Auto-refresh summary only every 60 seconds (measurements stay filtered)
  setInterval(async () => {
    await refreshSummary();
    // Don't reload measurements unless slider moved or filter changed
  }, 60000);
}

// Start the dashboard only once
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
