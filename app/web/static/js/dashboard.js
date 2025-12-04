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
      const inputs = daySchedule.querySelectorAll('.time-slots input, .add-slot-btn');
      inputs.forEach(input => {
        input.disabled = !toggle.checked;
      });
    });
  });
  
  // Add time slot functionality
  document.querySelectorAll('.add-slot-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const daySchedule = btn.closest('.day-schedule');
      const timeSlotsContainer = daySchedule.querySelector('.time-slots');
      
      const newSlot = createTimeSlotElement();
      timeSlotsContainer.appendChild(newSlot);
    });
  });
  
  // Remove time slot functionality (for initial slots)
  document.querySelectorAll('.slot-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      const slot = btn.closest('.time-slot');
      const timeSlotsContainer = slot.closest('.time-slots');
      
      // Don't remove if it's the last slot
      if (timeSlotsContainer.querySelectorAll('.time-slot').length > 1) {
        slot.remove();
      } else {
        showToast('At least one time slot is required', 'warning');
      }
    });
  });
  
  // Helper function to create a time slot element
  function createTimeSlotElement(startTime = '09:00', endTime = '17:00', interval = 30) {
    const slot = document.createElement('div');
    slot.className = 'time-slot';
    slot.innerHTML = `
      <input type="time" value="${startTime}" class="slot-start" />
      <span>to</span>
      <input type="time" value="${endTime}" class="slot-end" />
      <input type="number" min="5" max="120" value="${interval}" class="slot-interval" />
      <span>min</span>
      <button type="button" class="slot-remove" title="Remove time slot">×</button>
    `;
    
    // Add remove handler
    slot.querySelector('.slot-remove').addEventListener('click', () => {
      const container = slot.closest('.time-slots');
      if (container.querySelectorAll('.time-slot').length > 1) {
        slot.remove();
      } else {
        showToast('At least one time slot is required', 'warning');
      }
    });
    
    return slot;
  }
  
  // Load config into modal form
  async function loadConfigIntoModal() {
    try {
      const response = await fetch('/api/scheduler/config');
      if (!response.ok) return;
      
      const config = await response.json();
      
      // Set active mode
      document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === config.mode);
      });
      document.querySelectorAll('.scheduler-panel').forEach(panel => {
        panel.classList.toggle('active', panel.id === `${config.mode}-panel`);
      });
      
      // Populate Simple mode
      if (config.mode === 'simple' || config.enabled !== undefined) {
        const enabledCheckbox = document.getElementById('scheduler-enabled');
        if (enabledCheckbox) enabledCheckbox.checked = config.enabled !== false;
        if (config.interval) {
          intervalSlider.value = config.interval;
          intervalValue.value = config.interval;
        }
      }
      
      // Populate Weekly mode
      if (config.mode === 'weekly' || config.days) {
        if (config.days) {
          document.querySelectorAll('.weekday-selector input[type="checkbox"]').forEach(cb => {
            cb.checked = config.days.includes(parseInt(cb.value));
          });
        }
        if (config.startTime) document.getElementById('start-time').value = config.startTime;
        if (config.endTime) document.getElementById('end-time').value = config.endTime;
        if (config.interval && weeklySlider && weeklyValue) {
          weeklySlider.value = config.interval;
          weeklyValue.value = config.interval;
        }
      }
      
      // Populate Advanced mode
      if (config.mode === 'advanced' && config.schedule) {
        document.querySelectorAll('.day-schedule').forEach(daySchedule => {
          const day = daySchedule.dataset.day;
          const toggle = daySchedule.querySelector('.day-toggle');
          const timeSlotsContainer = daySchedule.querySelector('.time-slots');
          
          if (config.schedule[day]) {
            // Day is enabled
            toggle.checked = true;
            
            // Clear existing slots
            timeSlotsContainer.innerHTML = '';
            
            // Add slots from config
            const slots = config.schedule[day];
            slots.forEach(slotData => {
              const slot = createTimeSlotElement(slotData.startTime, slotData.endTime, slotData.interval);
              timeSlotsContainer.appendChild(slot);
            });
          } else {
            // Day is disabled - keep default slot
            toggle.checked = false;
          }
        });
      }
      
    } catch (error) {
      console.error('Failed to load config into modal:', error);
    }
  }
  
  // Open modal - load config first, then show
  openBtn?.addEventListener('click', async () => {
    // Hide modal content while loading
    const modalContent = modal.querySelector('.scheduler-modal-content');
    if (modalContent) modalContent.style.opacity = '0';
    
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
    
    await loadConfigIntoModal();
    
    // Show modal content after config is loaded
    if (modalContent) {
      modalContent.style.opacity = '1';
      modalContent.style.transition = 'opacity 0.15s ease';
    }
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
      
      document.querySelectorAll('.day-schedule').forEach(daySchedule => {
        const toggle = daySchedule.querySelector('.day-toggle');
        if (!toggle.checked) return;
        
        const day = daySchedule.dataset.day;
        const slots = [];
        
        daySchedule.querySelectorAll('.time-slot').forEach(slot => {
          slots.push({
            startTime: slot.querySelector('.slot-start').value,
            endTime: slot.querySelector('.slot-end').value,
            interval: parseInt(slot.querySelector('.slot-interval').value)
          });
        });
        
        config.schedule[day] = slots;
      });
    }
    
    // Save to backend API
    try {
      const response = await fetch('/api/scheduler/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
      });
      
      if (!response.ok) {
        throw new Error('Failed to save configuration');
      }
      
      showToast(`Scheduler configured in ${activeMode} mode!`, 'success');
      closeModal();
      
      // Update status pill
      updateSchedulerStatus(config);
    } catch (error) {
      console.error('Failed to save scheduler config:', error);
      showToast('Failed to save scheduler configuration', 'error');
    }
  });
}

function updateSchedulerStatus(config) {
  const statusPill = document.querySelector('.status-pill .status-text');
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
    const totalSlots = Object.values(config.schedule).reduce((sum, slots) => sum + slots.length, 0);
    statusPill.textContent = `Scheduler: Advanced · ${activeDays} days · ${totalSlots} time slots`;
  }
}

// Load saved scheduler config on startup
async function loadSchedulerConfig() {
  try {
    const response = await fetch('/api/scheduler/config');
    if (!response.ok) {
      throw new Error('Failed to load configuration');
    }
    
    const config = await response.json();
    updateSchedulerStatus(config);
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
  initViewToggle();
  initInternalNetwork();
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

// ============================================================================
// View Toggle - Internet / Homenet
// ============================================================================
function initViewToggle() {
  const viewBtns = document.querySelectorAll('.view-btn');
  const viewToggle = document.querySelector('.view-toggle');
  const internetView = document.getElementById('internet-view');
  const homenetView = document.getElementById('homenet-view');
  
  // Function to switch views
  function switchToView(view, saveState = true) {
    // Update button states
    viewBtns.forEach(b => {
      if (b.dataset.view === view) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });
    
    // Update toggle indicator
    if (view === 'homenet') {
      viewToggle.classList.add('homenet-active');
    } else {
      viewToggle.classList.remove('homenet-active');
    }
    
    // Switch views
    if (view === 'internet') {
      internetView.classList.add('active');
      homenetView.classList.remove('active');
      homenetView.style.display = 'none';
      internetView.style.display = 'block';
    } else {
      homenetView.classList.add('active');
      internetView.classList.remove('active');
      internetView.style.display = 'none';
      homenetView.style.display = 'block';
      
      // Load internal data and check server status when switching to homenet
      checkServerStatus();
      loadInternalSummary();
      loadDevices();
      loadInternalMeasurements();
    }
    
    // Save view state to localStorage
    if (saveState) {
      localStorage.setItem('netwatch_current_view', view);
    }
  }
  
  // Add click handlers
  viewBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      switchToView(btn.dataset.view);
    });
  });
  
  // Restore saved view on page load (without animation)
  const savedView = localStorage.getItem('netwatch_current_view');
  if (savedView === 'homenet') {
    // Disable transition during initial load
    viewToggle.classList.add('no-transition');
    switchToView('homenet', false);
    // Re-enable transitions after the view is set
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        viewToggle.classList.remove('no-transition');
      });
    });
  }
}

// ============================================================================
// Internal Network State
// ============================================================================
const internalState = {
  devices: [],
  measurements: [],
  serverStatus: 'offline',
  isTestRunning: false,
  selectedDeviceId: null,
};

const internalCharts = {
  lanDevices: null,
  wifiDevices: null,
  speed: null,
  latency: null,
  bufferbloat: null,
  deviceHistory: null,
};

// Helper function to check if a metric value is missing (null or undefined)
function isValueMissing(value) {
  return value === null || value === undefined;
}

// Helper function to destroy a chart if it exists
function destroyChartIfExists(chartRef) {
  if (chartRef) {
    chartRef.destroy();
  }
  return null;
}

// ============================================================================
// Internal Network - API Functions
// ============================================================================
async function loadInternalSummary() {
  try {
    const response = await fetch('/api/internal/summary');
    if (!response.ok) throw new Error('Failed to load summary');
    
    const data = await response.json();
    
    // Update device counts (data.devices contains { total, lan, wifi, unknown })
    const devices = data.devices || {};
    document.getElementById('internal-device-count').textContent = devices.total || 0;
    
    // Build device count display with all types
    const lanCount = devices.lan || 0;
    const wifiCount = devices.wifi || 0;
    const unknownCount = devices.unknown || 0;
    
    document.getElementById('lan-count').innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
        <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
        <line x1="6" y1="6" x2="6.01" y2="6"></line>
        <line x1="6" y1="18" x2="6.01" y2="18"></line>
      </svg>
      ${lanCount} LAN
    `;
    
    // Build WiFi/Unknown count display - show both if unknown devices exist
    let wifiDisplay = `${wifiCount} WiFi`;
    if (unknownCount > 0) {
      wifiDisplay += ` <span style="opacity: 0.6;">+ ${unknownCount} Unknown</span>`;
    }
    
    document.getElementById('wifi-count').innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M5 12.55a11 11 0 0 1 14.08 0"></path>
        <path d="M1.42 9a16 16 0 0 1 21.16 0"></path>
        <path d="M8.53 16.11a6 6 0 0 1 6.95 0"></path>
        <line x1="12" y1="20" x2="12.01" y2="20"></line>
      </svg>
      ${wifiDisplay}
    `;
    
    // Update latest metrics if available
    if (data.latest) {
      console.log('Latest data from API:', data.latest);
      // Map backend field names to frontend expected names
      const mappedData = {
        download_speed: data.latest.download_mbps,
        upload_speed: data.latest.upload_mbps,
        latency: data.latest.ping_idle_ms,
        jitter: data.latest.jitter_ms,
        gateway_ping: data.latest.gateway_ping_ms,
        local_latency: data.latest.local_latency_ms,
        bufferbloat_grade: data.latest.bufferbloat_grade
      };
      console.log('Mapped data for updateInternalMetrics:', mappedData);
      updateInternalMetrics(mappedData);
    } else {
      console.log('No latest data available');
    }
    
    // Update server status from server_status object
    if (data.server_status) {
      updateServerStatus(data.server_status.running ? 'online' : 'offline');
    }
    
  } catch (error) {
    console.error('Error loading internal summary:', error);
  }
}

async function loadDevices() {
  try {
    const response = await fetch('/api/internal/devices');
    if (!response.ok) throw new Error('Failed to load devices');
    
    internalState.devices = await response.json();
    renderDeviceTable();
    updateDeviceCharts();
    
  } catch (error) {
    console.error('Error loading devices:', error);
  }
}

async function loadInternalMeasurements() {
  try {
    // Load last 7 days of internal measurements
    const startDate = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    const params = new URLSearchParams();
    params.append('start', startDate.toISOString());
    params.append('limit', '500');
    
    const response = await fetch(`/api/internal/measurements?${params.toString()}`);
    if (!response.ok) throw new Error('Failed to load measurements');
    
    internalState.measurements = await response.json();
    updateInternalHistoryCharts();
    
  } catch (error) {
    console.error('Error loading internal measurements:', error);
  }
}

function updateInternalHistoryCharts() {
  const measurements = internalState.measurements;
  
  if (!measurements || measurements.length === 0) {
    console.log('No internal measurements to chart');
    return;
  }
  
  // Sort by timestamp ascending for charts
  const sorted = [...measurements].sort((a, b) => 
    new Date(a.timestamp) - new Date(b.timestamp)
  );
  
  const labels = sorted.map(m => new Date(m.timestamp));
  const downloadData = sorted.map(m => m.download_mbps || 0);
  const uploadData = sorted.map(m => m.upload_mbps || 0);
  const pingData = sorted.map(m => m.ping_idle_ms || null);  // Use null for missing to skip points
  const jitterData = sorted.map(m => m.jitter_ms || 0);
  const gatewayPingData = sorted.map(m => m.gateway_ping_ms || null);  // Use null for missing
  const localLatencyData = sorted.map(m => m.local_latency_ms || null);  // Use null for missing
  // Loaded ping: maximum of ping during download or upload (shows bufferbloat)
  const loadedPingData = sorted.map(m => {
    const dlPing = m.ping_during_download_ms;
    const ulPing = m.ping_during_upload_ms;
    // Return null if both are missing, otherwise max of available values
    if (isValueMissing(dlPing) && isValueMissing(ulPing)) return null;
    return Math.max(dlPing || 0, ulPing || 0);
  });
  
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
          padding: 15,
          font: { size: 11, weight: '500' },
          color: 'rgba(255, 255, 255, 0.8)',
        },
      },
      tooltip: {
        backgroundColor: 'rgba(15, 23, 42, 0.9)',
        titleFont: { size: 13, weight: '600' },
        bodyFont: { size: 12 },
        padding: 10,
        cornerRadius: 8,
        filter: function(tooltipItem) {
          // Show all items, even if value is null/0
          return true;
        },
        callbacks: {
          label: function(context) {
            const value = context.parsed.y;
            if (value === null || value === undefined) {
              return context.dataset.label + ': —';
            }
            return context.dataset.label + ': ' + value;
          }
        }
      },
    },
    scales: {
      x: {
        type: 'time',
        time: { unit: 'hour' },
        grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
        ticks: { maxRotation: 0, font: { size: 10 }, color: 'rgba(255, 255, 255, 0.6)' },
      },
      y: {
        beginAtZero: true,
        grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
        ticks: { font: { size: 10 }, color: 'rgba(255, 255, 255, 0.6)' },
      },
    },
    elements: {
      point: { radius: 3, hoverRadius: 6, borderWidth: 2 },
      line: { tension: 0.4, borderWidth: 2, spanGaps: false },
    },
  };
  
  // Internal Speed History Chart (Download & Upload)
  const speedCtx = document.getElementById('internal-speed-chart');
  if (speedCtx) {
    if (internalCharts.speed) {
      internalCharts.speed.data.labels = labels;
      internalCharts.speed.data.datasets[0].data = downloadData;
      internalCharts.speed.data.datasets[1].data = uploadData;
      internalCharts.speed.update();
    } else {
      internalCharts.speed = new Chart(speedCtx.getContext('2d'), {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Download (Mbps)',
              data: downloadData,
              borderColor: '#22d3ee',
              backgroundColor: 'rgba(34, 211, 238, 0.1)',
              fill: true,
            },
            {
              label: 'Upload (Mbps)',
              data: uploadData,
              borderColor: '#3b82f6',
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              fill: true,
            },
          ],
        },
        options: {
          ...chartOptions,
          scales: {
            ...chartOptions.scales,
            y: {
              ...chartOptions.scales.y,
              ticks: {
                ...chartOptions.scales.y.ticks,
                callback: (value) => `${value} Mbps`,
              },
            },
          },
        },
      });
    }
  }
  
  // Internal Latency History Chart (Ping, Jitter, Gateway, Local Latency)
  const latencyCtx = document.getElementById('internal-latency-chart');
  if (latencyCtx) {
    if (internalCharts.latency) {
      internalCharts.latency.data.labels = labels;
      internalCharts.latency.data.datasets[0].data = pingData;
      internalCharts.latency.data.datasets[1].data = jitterData;
      internalCharts.latency.data.datasets[2].data = gatewayPingData;
      internalCharts.latency.data.datasets[3].data = localLatencyData;
      internalCharts.latency.update();
    } else {
      internalCharts.latency = new Chart(latencyCtx.getContext('2d'), {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Ping (ms)',
              data: pingData,
              borderColor: '#f97316',
              backgroundColor: 'rgba(249, 115, 22, 0.1)',
              fill: true,
            },
            {
              label: 'Jitter (ms)',
              data: jitterData,
              borderColor: '#a855f7',
              backgroundColor: 'rgba(168, 85, 247, 0.1)',
              fill: true,
            },
            {
              label: 'Gateway Ping (ms)',
              data: gatewayPingData,
              borderColor: '#06b6d4',
              backgroundColor: 'rgba(6, 182, 212, 0.1)',
              fill: false,
              borderDash: [5, 5],
            },
            {
              label: 'Local Latency (ms)',
              data: localLatencyData,
              borderColor: '#84cc16',
              backgroundColor: 'rgba(132, 204, 22, 0.1)',
              fill: false,
              borderDash: [2, 8],  // More distinct dash pattern
            },
          ],
        },
        options: {
          ...chartOptions,
          scales: {
            ...chartOptions.scales,
            y: {
              ...chartOptions.scales.y,
              ticks: {
                ...chartOptions.scales.y.ticks,
                callback: (value) => `${value} ms`,
              },
            },
          },
        },
      });
    }
  }
  
  // Bufferbloat Chart (Latency Under Load) - Shows idle ping vs loaded ping
  const bufferbloatCtx = document.getElementById('internal-bufferbloat-chart');
  if (bufferbloatCtx) {
    if (internalCharts.bufferbloat) {
      internalCharts.bufferbloat.data.labels = labels;
      internalCharts.bufferbloat.data.datasets[0].data = pingData;
      internalCharts.bufferbloat.data.datasets[1].data = loadedPingData;
      internalCharts.bufferbloat.data.datasets[2].data = gatewayPingData;
      internalCharts.bufferbloat.update();
    } else {
      internalCharts.bufferbloat = new Chart(bufferbloatCtx.getContext('2d'), {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Idle Ping (ms)',
              data: pingData,
              borderColor: '#22c55e',
              backgroundColor: 'rgba(34, 197, 94, 0.1)',
              fill: false,
              borderWidth: 2,
            },
            {
              label: 'Loaded Ping (ms)',
              data: loadedPingData,
              borderColor: '#ef4444',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              fill: false,
              borderWidth: 2,
            },
            {
              label: 'Gateway Ping (ms)',
              data: gatewayPingData,
              borderColor: '#06b6d4',
              backgroundColor: 'rgba(6, 182, 212, 0.1)',
              fill: false,
              borderWidth: 2,
              borderDash: [5, 5],
            },
          ],
        },
        options: {
          ...chartOptions,
          scales: {
            ...chartOptions.scales,
            y: {
              ...chartOptions.scales.y,
              ticks: {
                ...chartOptions.scales.y.ticks,
                callback: (value) => `${value} ms`,
              },
            },
          },
        },
      });
    }
  }
}

async function ensureServerRunning() {
  // Check if server is running, start it if not
  if (internalState.serverStatus === 'online') {
    return true;
  }
  
  try {
    updateServerStatus('starting');
    const response = await fetch('/api/internal/server/start', { method: 'POST' });
    const data = await response.json();
    
    if (!response.ok || data.error) {
      throw new Error(data.error || 'Failed to start server');
    }
    
    updateServerStatus('online');
    showToast('Speed test server started automatically', 'info');
    return true;
  } catch (error) {
    console.error('Error auto-starting server:', error);
    showToast('Failed to start server: ' + error.message, 'error');
    updateServerStatus('offline');
    return false;
  }
}

async function scanDevices() {
  // Ensure server is running before scanning
  if (!await ensureServerRunning()) {
    return;
  }
  
  showToast('Scanning network for devices...', 'info');
  
  try {
    const response = await fetch('/api/internal/devices/scan', { method: 'POST' });
    if (!response.ok) throw new Error('Scan failed');
    
    const result = await response.json();
    showToast(`Found ${result.devices_found} devices!`, 'success');
    
    // Reload devices
    await loadDevices();
    await loadInternalSummary();
    
    // Update last scan time
    document.getElementById('last-scan-time').textContent = `Last scan: ${new Date().toLocaleTimeString()}`;
    
  } catch (error) {
    console.error('Error scanning devices:', error);
    showToast('Failed to scan network', 'error');
  }
}

async function toggleServer() {
  const toggleBtn = document.getElementById('toggle-server');
  
  if (internalState.serverStatus === 'online') {
    // Stop server
    try {
      updateServerStatus('starting');
      toggleBtn.disabled = true;
      const response = await fetch('/api/internal/server/stop', { method: 'POST' });
      const data = await response.json();
      
      if (!response.ok || data.error) {
        throw new Error(data.error || 'Failed to stop server');
      }
      
      updateServerStatus('offline');
      showToast('Speed test server stopped', 'info');
    } catch (error) {
      console.error('Error stopping server:', error);
      showToast('Failed to stop server: ' + error.message, 'error');
      updateServerStatus('online');
    } finally {
      toggleBtn.disabled = false;
    }
  } else {
    // Start server
    try {
      updateServerStatus('starting');
      toggleBtn.disabled = true;
      const response = await fetch('/api/internal/server/start', { method: 'POST' });
      const data = await response.json();
      
      if (!response.ok || data.error) {
        throw new Error(data.error || 'Failed to start server');
      }
      
      updateServerStatus('online');
      showToast('Speed test server started on port 5201', 'success');
    } catch (error) {
      console.error('Error starting server:', error);
      showToast('Failed to start server: ' + error.message, 'error');
      updateServerStatus('offline');
    } finally {
      toggleBtn.disabled = false;
    }
  }
}

function updateServerStatus(status) {
  internalState.serverStatus = status;
  
  const serverDot = document.querySelector('.server-dot');
  const serverText = document.querySelector('.server-text');
  const toggleBtn = document.getElementById('toggle-server');
  const runTestBtn = document.getElementById('run-internal-test');
  
  if (!serverDot || !serverText || !toggleBtn) return;
  
  serverDot.className = 'server-dot ' + status;
  
  if (status === 'online') {
    serverText.textContent = 'Server: Online';
    toggleBtn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="6" y="4" width="4" height="16"></rect>
        <rect x="14" y="4" width="4" height="16"></rect>
      </svg>
      Stop Server
    `;
    if (runTestBtn) runTestBtn.disabled = false;
  } else if (status === 'starting') {
    serverText.textContent = 'Server: Starting...';
    // Don't disable the button here - let toggleServer manage it
    if (runTestBtn) runTestBtn.disabled = true;
  } else {
    serverText.textContent = 'Server: Offline';
    toggleBtn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
        <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
        <line x1="6" y1="6" x2="6.01" y2="6"></line>
        <line x1="6" y1="18" x2="6.01" y2="18"></line>
      </svg>
      Start Server
    `;
    if (runTestBtn) runTestBtn.disabled = true;
  }
}

async function runInternalTest() {
  if (internalState.isTestRunning) return;
  
  // Ensure server is running before starting test
  if (!await ensureServerRunning()) {
    return;
  }
  
  internalState.isTestRunning = true;
  const liveSection = document.getElementById('live-test-section');
  const runBtn = document.getElementById('run-internal-test');
  
  liveSection.style.display = 'block';
  runBtn.disabled = true;
  
  updateLiveTest('Initializing...', 0);
  
  // Initialize live wave chart
  initLiveWaveChart();
  
  // Track results for final display
  const results = {
    download_speed: 0,
    upload_speed: 0,
    latency: 0,
    jitter: 0,
    bufferbloat_grade: '?',
    local_latency: 0,
  };
  
  try {
    // Use Server-Sent Events for streaming progress
    const eventSource = new EventSource('/api/internal/speedtest/stream');
    
    eventSource.onopen = () => {
      console.log('SSE connection opened');
    };
    
    eventSource.onerror = (event) => {
      console.error('SSE error:', event);
      eventSource.close();
      showToast('Connection lost during test', 'error');
      finishTest(false);
    };
    
    // Handle phase updates
    eventSource.addEventListener('phase', (event) => {
      const data = JSON.parse(event.data);
      document.getElementById('live-phase').textContent = capitalize(data.phase);
      updateLiveTest(data.message, null);
    });
    
    // Handle progress updates
    eventSource.addEventListener('progress', (event) => {
      const data = JSON.parse(event.data);
      updateLiveTest(null, data.percent);
    });
    
    // Handle metric updates (live values)
    eventSource.addEventListener('metric', (event) => {
      const data = JSON.parse(event.data);
      
      if (data.name === 'download') {
        results.download_speed = data.value;
        document.getElementById('live-download').textContent = `${formatNumber(data.value)} Mbps`;
        addToLiveWave('download', data.value);
      } else if (data.name === 'upload') {
        results.upload_speed = data.value;
        document.getElementById('live-upload').textContent = `${formatNumber(data.value)} Mbps`;
        addToLiveWave('upload', data.value);
      } else if (data.name === 'ping') {
        results.latency = data.value;
        document.getElementById('live-latency').textContent = `${formatNumber(data.value)} ms`;
      } else if (data.name === 'jitter') {
        results.jitter = data.value;
      } else if (data.name === 'local_latency') {
        results.local_latency = data.value;
      } else if (data.name === 'gateway_ping') {
        results.gateway_ping = data.value;
      } else if (data.name === 'grade') {
        results.bufferbloat_grade = data.value;
      }
    });
    
    // Handle upload phase start - reset chart for upload visualization
    eventSource.addEventListener('upload_start', (event) => {
      console.log('Upload phase starting - resetting chart');
      resetChartForUpload();
    });
    
    // Handle test completion
    eventSource.addEventListener('complete', (event) => {
      const data = JSON.parse(event.data);
      console.log('Test complete:', data);
      
      // Update with final results - handle both direct data and nested results
      if (data.results) {
        results.download_speed = data.results.download_mbps || results.download_speed;
        results.upload_speed = data.results.upload_mbps || results.upload_speed;
        results.latency = data.results.ping_idle_ms || results.latency;
        results.jitter = data.results.jitter_ms || results.jitter;
        results.bufferbloat_grade = data.results.bufferbloat_grade || results.bufferbloat_grade;
        results.local_latency = data.results.local_latency_ms || results.local_latency;
      } else {
        // Direct data from streaming complete event
        results.download_speed = data.download || results.download_speed;
        results.upload_speed = data.upload || results.upload_speed;
        results.latency = data.ping || results.latency;
        results.jitter = data.jitter || results.jitter;
      }
      
      eventSource.close();
      
      // Ramp down the graph smoothly
      rampDownLiveWave(() => {
        finishTest(true);
      });
    });
    
    // Handle errors from server
    eventSource.addEventListener('error', (event) => {
      const data = JSON.parse(event.data);
      console.error('Server error:', data.message);
      eventSource.close();
      showToast(`Test failed: ${data.message}`, 'error');
      finishTest(false);
    });
    
  } catch (error) {
    console.error('Error running internal test:', error);
    showToast('Internal speed test failed', 'error');
    finishTest(false);
  }
  
  function finishTest(success) {
    if (success) {
      // Update live displays with final values
      document.getElementById('live-download').textContent = `${formatNumber(results.download_speed)} Mbps`;
      document.getElementById('live-upload').textContent = `${formatNumber(results.upload_speed)} Mbps`;
      document.getElementById('live-latency').textContent = `${formatNumber(results.latency)} ms`;
      document.getElementById('live-phase').textContent = 'Complete';
      
      updateLiveTest('Test complete!', 100);
      showToast('Speed test completed!', 'success');
      
      // Update metrics display
      updateInternalMetrics(results);
      
      // Reload data including historical charts
      loadInternalSummary();
      loadDevices();
      loadInternalMeasurements();
      
      // Hide live section after a delay
      setTimeout(() => {
        liveSection.style.display = 'none';
      }, 4000);
    } else {
      updateLiveTest('Test failed', 0);
      setTimeout(() => {
        liveSection.style.display = 'none';
      }, 2000);
    }
    
    internalState.isTestRunning = false;
    runBtn.disabled = false;
  }
}

// Live wave chart for real-time metrics
let liveWaveChart = null;
const liveWaveData = {
  download: [],
  upload: [],
  labels: [],
};

function initLiveWaveChart() {
  const canvas = document.getElementById('live-wave-chart');
  if (!canvas) return;
  
  // Reset data and phase
  liveWaveData.download = [];
  liveWaveData.upload = [];
  liveWaveData.labels = [];
  currentTestPhase = 'download';
  
  // Destroy existing chart
  if (liveWaveChart) {
    liveWaveChart.destroy();
  }
  
  const ctx = canvas.getContext('2d');
  liveWaveChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: liveWaveData.labels,
      datasets: [
        {
          label: 'Download',
          data: liveWaveData.download,
          borderColor: '#22d3ee',
          backgroundColor: 'rgba(34, 211, 238, 0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          spanGaps: false,  // Don't connect across null values
        },
        {
          label: 'Upload',
          data: liveWaveData.upload,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          spanGaps: false,  // Don't connect across null values
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 100,
      },
      interaction: {
        intersect: false,
        mode: 'index',
      },
      scales: {
        x: {
          display: false,
        },
        y: {
          beginAtZero: true,
          grid: {
            color: 'rgba(255, 255, 255, 0.1)',
          },
          ticks: {
            color: 'rgba(255, 255, 255, 0.6)',
            callback: (value) => `${value} Mbps`,
          },
        },
      },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: 'rgba(255, 255, 255, 0.8)',
            usePointStyle: true,
            pointStyle: 'line',
          },
        },
        tooltip: {
          enabled: true,
          filter: (tooltipItem) => tooltipItem.raw !== null,  // Hide null values in tooltip
        },
      },
    },
  });
}

// Track which phase we're in
let currentTestPhase = 'download';

function addToLiveWave(type, value) {
  if (!liveWaveChart) return;
  
  const now = new Date().toLocaleTimeString();
  
  // Keep max 50 data points for smoother visualization
  if (liveWaveData.labels.length >= 50) {
    liveWaveData.labels.shift();
    liveWaveData.download.shift();
    liveWaveData.upload.shift();
  }
  
  // Update phase tracking
  currentTestPhase = type;
  
  // Always add new data point for more responsive updates
  liveWaveData.labels.push(now);
  
  if (type === 'download') {
    liveWaveData.download.push(value);
    liveWaveData.upload.push(null);  // Use null to not draw a line
  } else {
    liveWaveData.upload.push(value);
    liveWaveData.download.push(null);  // Use null to not draw a line
  }
  
  liveWaveChart.update('active');
}

function resetChartForUpload() {
  // Immediately clear chart data and start fresh for upload phase
  if (!liveWaveChart) return;
  
  // Update phase tracking
  currentTestPhase = 'upload';
  
  // Immediately reset all data arrays - no animation delay
  liveWaveData.labels = [];
  liveWaveData.download = [];
  liveWaveData.upload = [];
  
  // Update chart immediately with empty data
  liveWaveChart.data.labels = liveWaveData.labels;
  liveWaveChart.data.datasets[0].data = liveWaveData.download;
  liveWaveChart.data.datasets[1].data = liveWaveData.upload;
  liveWaveChart.update('none');
  
  console.log('[LiveWave] Chart reset for upload phase - starting fresh');
}

function rampDownLiveWave(callback) {
  if (!liveWaveChart || (liveWaveData.download.length === 0 && liveWaveData.upload.length === 0)) {
    if (callback) callback();
    return;
  }
  
  const steps = 10;
  const interval = 100; // 100ms per step = 1 second total
  let currentStep = 0;
  
  const rampInterval = setInterval(() => {
    currentStep++;
    const factor = 1 - (currentStep / steps);
    
    // Reduce all values proportionally (skip null values)
    for (let i = 0; i < liveWaveData.download.length; i++) {
      if (liveWaveData.download[i] !== null) {
        liveWaveData.download[i] *= factor;
      }
    }
    for (let i = 0; i < liveWaveData.upload.length; i++) {
      if (liveWaveData.upload[i] !== null) {
        liveWaveData.upload[i] *= factor;
      }
    }
    
    liveWaveChart.update('none');
    
    if (currentStep >= steps) {
      clearInterval(rampInterval);
      // Set all non-null values to 0
      for (let i = 0; i < liveWaveData.download.length; i++) {
        if (liveWaveData.download[i] !== null) liveWaveData.download[i] = 0;
      }
      for (let i = 0; i < liveWaveData.upload.length; i++) {
        if (liveWaveData.upload[i] !== null) liveWaveData.upload[i] = 0;
      }
      liveWaveChart.update('none');
      if (callback) callback();
    }
  }, interval);
}

function capitalize(str) {
  if (!str) return str;
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function updateLiveTest(status, progress) {
  if (status !== null && status !== undefined) {
    document.getElementById('live-test-status').textContent = status;
  }
  if (progress !== null && progress !== undefined) {
    document.getElementById('live-test-bar').style.width = `${progress}%`;
  }
}

function updateInternalMetrics(data) {
  // Update metric values
  const downloadEl = document.getElementById('internal-download-value');
  const uploadEl = document.getElementById('internal-upload-value');
  const pingEl = document.getElementById('internal-ping-value');
  const jitterEl = document.getElementById('internal-jitter-value');
  const gatewayPingEl = document.getElementById('internal-gateway-ping-value');
  const localLatencyEl = document.getElementById('internal-local-latency-value');
  const gradeEl = document.getElementById('internal-bufferbloat-grade');
  
  if (downloadEl) {
    const current = parseFloat(downloadEl.textContent) || 0;
    animateValue(downloadEl, current, data.download_speed || 0);
  }
  if (uploadEl) {
    const current = parseFloat(uploadEl.textContent) || 0;
    animateValue(uploadEl, current, data.upload_speed || 0);
  }
  if (pingEl) {
    const current = parseFloat(pingEl.textContent) || 0;
    animateValue(pingEl, current, data.latency || 0);
  }
  if (jitterEl) {
    const current = parseFloat(jitterEl.textContent) || 0;
    animateValue(jitterEl, current, data.jitter || 0);
  }
  if (gatewayPingEl) {
    const current = parseFloat(gatewayPingEl.textContent) || 0;
    animateValue(gatewayPingEl, current, data.gateway_ping || 0);
  }
  if (localLatencyEl) {
    const current = parseFloat(localLatencyEl.textContent) || 0;
    animateValue(localLatencyEl, current, data.local_latency || 0);
  }
  if (gradeEl && data.bufferbloat_grade) {
    gradeEl.textContent = data.bufferbloat_grade;
    gradeEl.className = 'metric-value grade-value grade-' + data.bufferbloat_grade.toLowerCase().replace('+', '-plus');
  }
  
  // Update progress bars
  updateProgressBar('internal-download-progress', data.download_speed || 0, 1000);
  updateProgressBar('internal-upload-progress', data.upload_speed || 0, 1000);
  updateProgressBar('internal-ping-progress', data.latency || 0, 10);
  updateProgressBar('internal-jitter-progress', data.jitter || 0, 5);
  updateProgressBar('internal-gateway-ping-progress', data.gateway_ping || 0, 10);
  updateProgressBar('internal-local-latency-progress', data.local_latency || 0, 10);
}

// ============================================================================
// Device Table Rendering
// ============================================================================
function renderDeviceTable() {
  const tbody = document.getElementById('device-table');
  const emptyState = document.getElementById('device-empty-state');
  
  if (!internalState.devices.length) {
    tbody.innerHTML = '';
    emptyState.classList.add('visible');
    return;
  }
  
  emptyState.classList.remove('visible');
  
  const rows = internalState.devices.map(device => {
    const isLan = device.connection_type === 'lan';
    const displayName = device.friendly_name || device.hostname || 'Unknown';
    const typeIcon = isLan ? `
      <div class="device-type-icon lan">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
          <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
          <line x1="6" y1="6" x2="6.01" y2="6"></line>
          <line x1="6" y1="18" x2="6.01" y2="18"></line>
        </svg>
      </div>
    ` : `
      <div class="device-type-icon wifi">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12.55a11 11 0 0 1 14.08 0"></path>
          <path d="M1.42 9a16 16 0 0 1 21.16 0"></path>
          <path d="M8.53 16.11a6 6 0 0 1 6.95 0"></path>
          <line x1="12" y1="20" x2="12.01" y2="20"></line>
        </svg>
      </div>
    `;
    
    return `
      <tr data-device-id="${device.id}">
        <td>${typeIcon}</td>
        <td>
          <span class="device-name">${displayName}</span>
          ${device.hostname ? `<span class="device-hostname">${device.hostname}</span>` : ''}
        </td>
        <td>${device.ip_address}</td>
        <td><code>${device.mac_address || '—'}</code></td>
        <td>${device.last_download ? formatNumber(device.last_download) + ' Mbps' : '—'}</td>
        <td>${device.last_upload ? formatNumber(device.last_upload) + ' Mbps' : '—'}</td>
        <td>${device.last_ping ? formatNumber(device.last_ping) + ' ms' : '—'}</td>
        <td>${device.last_test ? new Date(device.last_test).toLocaleString() : 'Never'}</td>
        <td>
          <button class="device-action-btn" onclick="showDeviceDetails(${device.id})" title="View Details">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
              <circle cx="12" cy="12" r="3"></circle>
            </svg>
          </button>
        </td>
      </tr>
    `;
  }).join('');
  
  tbody.innerHTML = rows;
}

// ============================================================================
// Device Charts
// ============================================================================
function updateDeviceCharts() {
  const lanDevices = internalState.devices.filter(d => d.connection_type === 'lan');
  const wifiDevices = internalState.devices.filter(d => d.connection_type === 'wifi');
  
  // LAN Devices Chart
  const lanCtx = document.getElementById('lan-devices-chart');
  if (lanCtx) {
    if (lanDevices.length === 0) {
      // No LAN devices found - destroy chart and show placeholder
      internalCharts.lanDevices = destroyChartIfExists(internalCharts.lanDevices);
      showChartPlaceholder(lanCtx, 'No LAN devices found');
    } else {
      const labels = lanDevices.map(d => d.friendly_name || d.hostname || d.ip_address);
      const downloadData = lanDevices.map(d => d.last_download);
      const uploadData = lanDevices.map(d => d.last_upload);
      
      // Check if we have any actual data
      const hasData = downloadData.some(v => v !== null && v !== undefined) || 
                      uploadData.some(v => v !== null && v !== undefined);
      
      if (!hasData) {
        // Devices exist but no tests run - destroy chart and show placeholder with device names
        internalCharts.lanDevices = destroyChartIfExists(internalCharts.lanDevices);
        showChartPlaceholder(lanCtx, `${lanDevices.length} device(s) - Run tests to see speeds`);
      } else {
        if (internalCharts.lanDevices) {
          internalCharts.lanDevices.data.labels = labels;
          internalCharts.lanDevices.data.datasets[0].data = downloadData.map(v => v || 0);
          internalCharts.lanDevices.data.datasets[1].data = uploadData.map(v => v || 0);
          internalCharts.lanDevices.update();
        } else {
          internalCharts.lanDevices = new Chart(lanCtx.getContext('2d'), {
            type: 'bar',
            data: {
              labels,
              datasets: [
                {
                  label: 'Download',
                  data: downloadData.map(v => v || 0),
                  backgroundColor: 'rgba(16, 185, 129, 0.5)',
                  borderColor: '#10b981',
                  borderWidth: 1,
                },
                {
                  label: 'Upload',
                  data: uploadData.map(v => v || 0),
                  backgroundColor: 'rgba(34, 211, 238, 0.5)',
                  borderColor: '#22d3ee',
                  borderWidth: 1,
                }
              ]
            },
            options: getBarChartOptions()
          });
        }
      }
    }
  }
  
  // WiFi Devices Chart
  const wifiCtx = document.getElementById('wifi-devices-chart');
  if (wifiCtx) {
    if (wifiDevices.length === 0) {
      // No WiFi devices found - destroy chart and show placeholder
      internalCharts.wifiDevices = destroyChartIfExists(internalCharts.wifiDevices);
      showChartPlaceholder(wifiCtx, 'No WiFi devices found');
    } else {
      const labels = wifiDevices.map(d => d.friendly_name || d.hostname || d.ip_address);
      const downloadData = wifiDevices.map(d => d.last_download);
      const uploadData = wifiDevices.map(d => d.last_upload);
      
      const hasData = downloadData.some(v => v !== null && v !== undefined) || 
                      uploadData.some(v => v !== null && v !== undefined);
      
      if (!hasData) {
        // Devices exist but no tests run - destroy chart and show placeholder with device names
        internalCharts.wifiDevices = destroyChartIfExists(internalCharts.wifiDevices);
        showChartPlaceholder(wifiCtx, `${wifiDevices.length} device(s) - Run tests to see speeds`);
      } else {
        if (internalCharts.wifiDevices) {
          internalCharts.wifiDevices.data.labels = labels;
          internalCharts.wifiDevices.data.datasets[0].data = downloadData.map(v => v || 0);
          internalCharts.wifiDevices.data.datasets[1].data = uploadData.map(v => v || 0);
          internalCharts.wifiDevices.update();
        } else {
          internalCharts.wifiDevices = new Chart(wifiCtx.getContext('2d'), {
            type: 'bar',
            data: {
              labels,
              datasets: [
                {
                  label: 'Download',
                  data: downloadData.map(v => v || 0),
                  backgroundColor: 'rgba(59, 130, 246, 0.5)',
                  borderColor: '#3b82f6',
                  borderWidth: 1,
                },
                {
                  label: 'Upload',
                  data: uploadData.map(v => v || 0),
                  backgroundColor: 'rgba(168, 85, 247, 0.5)',
                  borderColor: '#a855f7',
                  borderWidth: 1,
                }
              ]
            },
            options: getBarChartOptions()
          });
        }
      }
    }
  }
}

function showChartPlaceholder(canvas, message) {
  const ctx = canvas.getContext('2d');
  const parent = canvas.parentElement;
  
  // Clear the canvas
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  
  // Draw placeholder message
  ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
  ctx.font = '14px Inter, system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(message, canvas.width / 2, canvas.height / 2);
}

function getBarChartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        position: 'top',
        labels: {
          usePointStyle: true,
          padding: 15,
          font: { size: 11, weight: '500' }
        }
      },
      tooltip: {
        backgroundColor: 'rgba(15, 23, 42, 0.9)',
        titleFont: { size: 13, weight: '600' },
        bodyFont: { size: 12 },
        padding: 10,
        cornerRadius: 8,
        callbacks: {
          label: function(context) {
            return `${context.dataset.label}: ${context.raw.toFixed(2)} Mbps`;
          }
        }
      }
    },
    scales: {
      x: {
        grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
        ticks: { font: { size: 10 }, maxRotation: 45 }
      },
      y: {
        beginAtZero: true,
        grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
        ticks: {
          font: { size: 10 },
          callback: function(value) { return value + ' Mbps'; }
        }
      }
    }
  };
}

// ============================================================================
// Device Detail Modal
// ============================================================================
async function showDeviceDetails(deviceId) {
  const modal = document.getElementById('device-modal');
  internalState.selectedDeviceId = deviceId;
  
  try {
    const response = await fetch(`/api/internal/devices/${deviceId}`);
    if (!response.ok) throw new Error('Failed to load device');
    
    const device = await response.json();
    
    // Update modal content
    document.getElementById('device-modal-title').textContent = device.friendly_name || device.hostname || 'Unknown Device';
    document.getElementById('device-ip').textContent = device.ip_address;
    document.getElementById('device-mac').textContent = device.mac_address || '—';
    document.getElementById('device-conn-type').textContent = device.connection_type?.toUpperCase() || '—';
    document.getElementById('device-vendor').textContent = device.vendor || '—';
    document.getElementById('device-first-seen').textContent = device.first_seen ? new Date(device.first_seen).toLocaleString() : '—';
    document.getElementById('device-last-seen').textContent = device.last_seen ? new Date(device.last_seen).toLocaleString() : '—';
    
    // Update stats
    document.getElementById('device-best-download').textContent = device.best_download ? `${formatNumber(device.best_download)} Mbps` : '— Mbps';
    document.getElementById('device-best-upload').textContent = device.best_upload ? `${formatNumber(device.best_upload)} Mbps` : '— Mbps';
    document.getElementById('device-avg-ping').textContent = device.avg_ping ? `${formatNumber(device.avg_ping)} ms` : '— ms';
    document.getElementById('device-avg-jitter').textContent = device.avg_jitter ? `${formatNumber(device.avg_jitter)} ms` : '— ms';
    
    // Update icon
    const iconEl = document.getElementById('device-modal-icon');
    if (device.connection_type === 'lan') {
      iconEl.className = 'lan-icon';
      iconEl.innerHTML = `
        <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
        <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
        <line x1="6" y1="6" x2="6.01" y2="6"></line>
        <line x1="6" y1="18" x2="6.01" y2="18"></line>
      `;
    } else {
      iconEl.className = 'wifi-icon';
      iconEl.innerHTML = `
        <path d="M5 12.55a11 11 0 0 1 14.08 0"></path>
        <path d="M1.42 9a16 16 0 0 1 21.16 0"></path>
        <path d="M8.53 16.11a6 6 0 0 1 6.95 0"></path>
        <line x1="12" y1="20" x2="12.01" y2="20"></line>
      `;
    }
    
    // Load measurements for this device
    if (device.measurements && device.measurements.length) {
      renderDeviceMeasurements(device.measurements);
      renderDeviceHistoryChart(device.measurements);
    }
    
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
    
  } catch (error) {
    console.error('Error loading device details:', error);
    showToast('Failed to load device details', 'error');
  }
}

function renderDeviceMeasurements(measurements) {
  const tbody = document.getElementById('device-measurements-table');
  if (!tbody) return;
  if (!measurements || !measurements.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-row">No measurements recorded yet.</td></tr>`;
    return;
  }
  
  const rows = measurements.slice(0, 10).map(m => `
    <tr>
      <td>${new Date(m.timestamp).toLocaleString()}</td>
      <td>${formatNumber(m.download_speed)} Mbps</td>
      <td>${formatNumber(m.upload_speed)} Mbps</td>
      <td>${formatNumber(m.ping_idle_ms)} ms</td>
      <td>${m.ping_loaded_ms != null ? formatNumber(m.ping_loaded_ms) + ' ms' : '—'}</td>
      <td>${formatNumber(m.jitter)} ms</td>
      <td><span class="grade-value grade-${(m.bufferbloat_grade || 'F').toLowerCase().replace('+', '-plus')}">${m.bufferbloat_grade || '—'}</span></td>
    </tr>
  `).join('');
  
  tbody.innerHTML = rows;
}

function renderDeviceHistoryChart(measurements) {
  const ctx = document.getElementById('device-history-chart');
  if (!ctx) return;
  if (internalCharts.deviceHistory) {
    internalCharts.deviceHistory.destroy();
    internalCharts.deviceHistory = null;
  }
  if (!measurements || !measurements.length) {
    const chartCtx = ctx.getContext('2d');
    chartCtx.clearRect(0, 0, ctx.width, ctx.height);
    return;
  }
  
  const labels = measurements.map(m => new Date(m.timestamp));
  const downloadData = measurements.map(m => m.download_speed);
  const uploadData = measurements.map(m => m.upload_speed);
  const pingIdleData = measurements.map(m => m.ping_idle_ms || null);
  const pingLoadedData = measurements.map(m => m.ping_loaded_ms || null);
  
  internalCharts.deviceHistory = new Chart(ctx.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Download (Mbps)',
          data: downloadData,
          borderColor: '#22d3ee',
          backgroundColor: 'rgba(34, 211, 238, 0.1)',
          fill: true,
          tension: 0.4,
          yAxisID: 'y-speed',
        },
        {
          label: 'Upload (Mbps)',
          data: uploadData,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          fill: true,
          tension: 0.4,
          yAxisID: 'y-speed',
        },
        {
          label: 'Idle Ping (ms)',
          data: pingIdleData,
          borderColor: '#22c55e',
          backgroundColor: 'rgba(34, 197, 94, 0.1)',
          fill: false,
          tension: 0.4,
          yAxisID: 'y-latency',
          borderWidth: 2,
        },
        {
          label: 'Loaded Ping (ms)',
          data: pingLoadedData,
          borderColor: '#ef4444',
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          fill: false,
          tension: 0.4,
          yAxisID: 'y-latency',
          borderWidth: 2,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
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
            padding: 10,
            font: { size: 11 },
          }
        },
        tooltip: {
          backgroundColor: 'rgba(15, 23, 42, 0.9)',
          padding: 10,
          cornerRadius: 8,
          callbacks: {
            /**
             * Format tooltip label for chart data points
             * @param {Object} context - Chart.js tooltip context
             * @param {number|null} context.parsed.y - The Y-axis value
             * @param {Object} context.dataset - Dataset containing the label
             * @returns {string} Formatted label string
             */
            label: function(context) {
              const value = context.parsed.y;
              if (value === null || value === undefined || typeof value !== 'number') {
                return context.dataset.label + ': —';
              }
              return context.dataset.label + ': ' + value.toFixed(2);
            }
          }
        }
      },
      scales: {
        x: {
          type: 'time',
          time: { unit: 'hour' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        'y-speed': {
          type: 'linear',
          position: 'left',
          beginAtZero: true,
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: {
            callback: (value) => `${value} Mbps`
          },
          title: {
            display: true,
            text: 'Speed (Mbps)',
            color: 'rgba(255, 255, 255, 0.7)',
          }
        },
        'y-latency': {
          type: 'linear',
          position: 'right',
          beginAtZero: true,
          grid: { drawOnChartArea: false },
          ticks: {
            callback: (value) => `${value} ms`
          },
          title: {
            display: true,
            text: 'Latency (ms)',
            color: 'rgba(255, 255, 255, 0.7)',
          }
        }
      }
    }
  });
}

function closeDeviceModal() {
  const modal = document.getElementById('device-modal');
  modal.classList.remove('active');
  document.body.style.overflow = '';
  internalState.selectedDeviceId = null;
}

function exportInternalCsv() {
  window.location.href = '/api/internal/export/csv';
  showToast('Downloading internal network CSV...', 'success');
}

// ============================================================================
// Internal Network Initialization
// ============================================================================
function initInternalNetwork() {
  // Button event listeners
  document.getElementById('scan-devices')?.addEventListener('click', scanDevices);
  document.getElementById('toggle-server')?.addEventListener('click', toggleServer);
  document.getElementById('run-internal-test')?.addEventListener('click', runInternalTest);
  document.getElementById('export-internal-csv')?.addEventListener('click', exportInternalCsv);
  
  // Device modal
  document.getElementById('close-device-modal')?.addEventListener('click', closeDeviceModal);
  document.getElementById('close-device-detail')?.addEventListener('click', closeDeviceModal);
  document.getElementById('run-device-test')?.addEventListener('click', async () => {
    if (internalState.selectedDeviceId) {
      closeDeviceModal();
      await runInternalTest();
    }
  });
  
  // Close modal on backdrop click
  document.getElementById('device-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'device-modal') {
      closeDeviceModal();
    }
  });
  
  // Check server status on load
  checkServerStatus();
}

async function checkServerStatus() {
  try {
    const response = await fetch('/api/internal/server/status');
    if (!response.ok) return;
    
    const data = await response.json();
    updateServerStatus(data.running ? 'online' : 'offline');
  } catch (error) {
    console.error('Error checking server status:', error);
  }
}

// Start the dashboard only once
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
