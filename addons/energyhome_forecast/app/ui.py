from __future__ import annotations

from typing import Dict, List

import plotly.graph_objects as go


def render_dashboard(
    history: Dict[str, List],
    forecast: Dict[str, List],
    status: Dict[str, str | int],
) -> str:
    history_times = history.get("timestamps", [])
    forecast_times = forecast.get("timestamps", [])

    # Check if grid power data is available
    has_grid_data = any(
        v is not None for v in (history.get("grid_l1_w", []) + history.get("grid_l2_w", []) + history.get("grid_l3_w", []))
    )

    # Plot 1: Total Load Actual vs Total Load Forecast
    fig1 = go.Figure()
    fig1.add_trace(
        go.Scatter(
            x=history_times,
            y=history.get("total_w", []),
            name="Total Load (Actual)",
            line=dict(color="#2563eb", width=2),
        )
    )
    fig1.add_trace(
        go.Scatter(
            x=forecast_times,
            y=forecast.get("total_w", []),
            name="Total Load (Forecast)",
            line=dict(color="#7c3aed", width=2, dash="dash"),
        )
    )
    fig1.update_layout(
        title="Total Load: Actual vs Forecast",
        xaxis_title="Time",
        yaxis_title="Power (W)",
        height=350,
        margin=dict(t=40, l=60, r=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    # Plot 2: Load per phase vs Grid power per phase
    fig2 = go.Figure()

    # Load phases
    colors_load = {"l1_w": "#ef4444", "l2_w": "#f59e0b", "l3_w": "#10b981"}
    colors_grid = {"grid_l1_w": "#dc2626", "grid_l2_w": "#d97706", "grid_l3_w": "#059669"}

    for phase in ["l1_w", "l2_w", "l3_w"]:
        phase_label = phase.replace("_w", "").upper()
        fig2.add_trace(
            go.Scatter(
                x=history_times,
                y=history.get(phase, []),
                name=f"{phase_label} Load",
                line=dict(color=colors_load[phase], width=2),
            )
        )

    # Grid phases
    if has_grid_data:
        for grid_phase in ["grid_l1_w", "grid_l2_w", "grid_l3_w"]:
            phase_label = grid_phase.replace("grid_", "").replace("_w", "").upper()
            fig2.add_trace(
                go.Scatter(
                    x=history_times,
                    y=history.get(grid_phase, []),
                    name=f"{phase_label} Grid",
                    line=dict(color=colors_grid[grid_phase], width=1.5, dash="dot"),
                )
            )

    fig2.update_layout(
        title="Phase Load vs Grid Power (Actual)",
        xaxis_title="Time",
        yaxis_title="Power (W)",
        height=350,
        margin=dict(t=40, l=60, r=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    # Plot 3: Phase Imbalance
    fig3 = go.Figure()
    imbalance = []
    for l1, l2, l3 in zip(
        history.get("l1_w", []), history.get("l2_w", []), history.get("l3_w", [])
    ):
        if l1 is None or l2 is None or l3 is None:
            imbalance.append(None)
        else:
            imbalance.append(max(l1, l2, l3) - min(l1, l2, l3))

    fig3.add_trace(
        go.Scatter(
            x=history_times,
            y=imbalance,
            name="Phase Imbalance",
            line=dict(color="#8b5cf6", width=2),
            fill="tozeroy",
            fillcolor="rgba(139, 92, 246, 0.1)",
        )
    )
    fig3.update_layout(
        title="Phase Imbalance (Max - Min Load)",
        xaxis_title="Time",
        yaxis_title="Imbalance (W)",
        height=350,
        margin=dict(t=40, l=60, r=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    # Warning banner if grid data is missing
    grid_warning = ""
    if not has_grid_data:
        grid_warning = """
        <div class="warning-banner">
            ⚠️ Grid phase power not configured. Configure <code>grid_l1_power</code>, <code>grid_l2_power</code>,
            <code>grid_l3_power</code> entities (or <code>grid_l*_current</code> with <code>grid_voltage_v</code>)
            to see grid traces in Plot 2.
        </div>
        """

    # Status cards
    status_cards = f"""
    <div class="status-cards">
        <div class="card">
            <div class="card-label">Last Poll</div>
            <div class="card-value">{status.get("last_poll_utc", "n/a")}</div>
        </div>
        <div class="card">
            <div class="card-label">Last ILC Update</div>
            <div class="card-value">{status.get("last_ilc_update_local", "n/a")}</div>
        </div>
        <div class="card">
            <div class="card-label">Points Stored</div>
            <div class="card-value">{status.get("points_stored", 0):,}</div>
        </div>
    </div>
    """

    # Live readings panel (populated by JavaScript)
    live_readings = """
    <div class="card live-readings" id="liveReadings">
        <h2 class="section-title">📡 Live Readings</h2>
        <div class="warning-banner" id="liveError" style="display: none;"></div>
        <div class="loading" id="loadingIndicator">Loading latest sensor values...</div>
        <div class="readings-grid" id="readingsGrid" style="display: none;">
            <!-- Populated by JavaScript -->
        </div>
    </div>
    """

    # Action buttons with explanations
    action_buttons = """
    <div class="actions-section">
        <div class="actions-buttons">
            <button class="btn btn-primary" onclick="pollNow()">📊 Poll now</button>
            <button class="btn btn-secondary" onclick="updateILC()">🎓 Update learning (ILC)</button>
            <button class="btn btn-secondary" onclick="refreshForecast()">🔄 Refresh forecast</button>
        </div>
        <div class="actions-help">
            <div class="help-item">
                <strong>📊 Poll now:</strong> Immediately fetch the latest sensor values from Home Assistant and store them in the database.
                Use this to verify sensor readings or to force an update outside the normal 15-minute polling cycle.
            </div>
            <div class="help-item">
                <strong>🎓 Update learning (ILC):</strong> Recalculate the Iterative Learning Control correction curves from historical forecast errors.
                This normally runs once per day automatically. The ILC algorithm learns from past mistakes to improve future forecasts.
            </div>
            <div class="help-item">
                <strong>🔄 Refresh forecast:</strong> Regenerate the 48-hour forecast using the current baseline patterns and ILC corrections.
                This does NOT fetch new sensor data—it just recomputes the forecast from existing data.
            </div>
        </div>
    </div>
    """

    # JavaScript functions
    javascript = """
    <script>
    // Fetch and display live readings on page load
    async function loadLiveReadings() {
        const resp = await fetch('./api/latest');
        const text = await resp.text();

        try {
            const data = JSON.parse(text);
            renderLiveReadings(data);
        } catch (e) {
            const errBox = document.getElementById('liveError');
            errBox.style.display = 'block';
            errBox.textContent =
                '⚠️ Live readings endpoint did not return JSON. HTTP ' +
                resp.status +
                '. Response (first 200 chars): ' +
                text.slice(0, 200);
            document.getElementById('loadingIndicator').style.display = 'none';
            throw e;
        }
    }

    function renderLiveReadings(data) {
        document.getElementById('loadingIndicator').style.display = 'none';
        document.getElementById('readingsGrid').style.display = 'grid';

        const signals = data.signals || {};
        const gridHtml = [];

        // Helper to format value
        function fmt(val, unit, estimated = false) {
            if (val === null || val === undefined) {
                return '<span class="value-missing">—</span>';
            }
            const estLabel = estimated ? ' <span class="estimated">(est.)</span>' : '';
            return `<span class="value-present">${val.toFixed(1)} ${unit}</span>${estLabel}`;
        }

        // Total load
        gridHtml.push(`
            <div class="reading-item">
                <div class="reading-label">Total Load</div>
                <div class="reading-value">${fmt(signals.total_w, 'W')}</div>
            </div>
        `);

        // Phase loads
        gridHtml.push(`
            <div class="reading-item">
                <div class="reading-label">L1 Load</div>
                <div class="reading-value">${fmt(signals.l1_w, 'W')}</div>
            </div>
        `);
        gridHtml.push(`
            <div class="reading-item">
                <div class="reading-label">L2 Load</div>
                <div class="reading-value">${fmt(signals.l2_w, 'W')}</div>
            </div>
        `);
        gridHtml.push(`
            <div class="reading-item">
                <div class="reading-label">L3 Load</div>
                <div class="reading-value">${fmt(signals.l3_w, 'W')}</div>
            </div>
        `);

        // Grid currents (if available)
        if (signals.grid_l1_a !== null || signals.grid_l2_a !== null || signals.grid_l3_a !== null) {
            gridHtml.push(`
                <div class="reading-item">
                    <div class="reading-label">Grid L1 Current</div>
                    <div class="reading-value">${fmt(signals.grid_l1_a, 'A')}</div>
                </div>
            `);
            gridHtml.push(`
                <div class="reading-item">
                    <div class="reading-label">Grid L2 Current</div>
                    <div class="reading-value">${fmt(signals.grid_l2_a, 'A')}</div>
                </div>
            `);
            gridHtml.push(`
                <div class="reading-item">
                    <div class="reading-label">Grid L3 Current</div>
                    <div class="reading-value">${fmt(signals.grid_l3_a, 'A')}</div>
                </div>
            `);
        }

        // Grid powers
        if (signals.grid_l1_w !== null || signals.grid_l2_w !== null || signals.grid_l3_w !== null) {
            gridHtml.push(`
                <div class="reading-item">
                    <div class="reading-label">Grid L1 Power</div>
                    <div class="reading-value">${fmt(signals.grid_l1_w, 'W', signals.grid_l1_w_estimated)}</div>
                </div>
            `);
            gridHtml.push(`
                <div class="reading-item">
                    <div class="reading-label">Grid L2 Power</div>
                    <div class="reading-value">${fmt(signals.grid_l2_w, 'W', signals.grid_l2_w_estimated)}</div>
                </div>
            `);
            gridHtml.push(`
                <div class="reading-item">
                    <div class="reading-label">Grid L3 Power</div>
                    <div class="reading-value">${fmt(signals.grid_l3_w, 'W', signals.grid_l3_w_estimated)}</div>
                </div>
            `);
        }

        // Inverter load (if configured)
        if (signals.inverter_w !== null) {
            gridHtml.push(`
                <div class="reading-item">
                    <div class="reading-label">Inverter Load</div>
                    <div class="reading-value">${fmt(signals.inverter_w, 'W')}</div>
                </div>
            `);
        }

        // SOC (if configured)
        if (signals.soc_pct !== null) {
            gridHtml.push(`
                <div class="reading-item">
                    <div class="reading-label">Battery SOC</div>
                    <div class="reading-value">${fmt(signals.soc_pct, '%')}</div>
                </div>
            `);
        }

        document.getElementById('readingsGrid').innerHTML = gridHtml.join('');
    }

    async function pollNow() {
        try {
            const res = await fetch('./api/poll_now', {method: 'POST'});
            if (res.ok) {
                alert('✅ Poll completed successfully! Reloading page...');
                location.reload();
            } else {
                alert('❌ Poll failed: ' + await res.text());
            }
        } catch (err) {
            alert('❌ Error: ' + err.message);
        }
    }

    async function updateILC() {
        try {
            const res = await fetch('./api/ilc/update', {method: 'POST'});
            if (res.ok) {
                alert('✅ ILC update completed! Reloading page...');
                location.reload();
            } else {
                alert('❌ ILC update failed: ' + await res.text());
            }
        } catch (err) {
            alert('❌ Error: ' + err.message);
        }
    }

    async function refreshForecast() {
        try {
            const res = await fetch('./api/recompute', {method: 'POST'});
            if (res.ok) {
                alert('✅ Forecast refreshed! Reloading page...');
                location.reload();
            } else {
                alert('❌ Refresh failed: ' + await res.text());
            }
        } catch (err) {
            alert('❌ Error: ' + err.message);
        }
    }

    // Load live readings when page loads
    window.addEventListener('DOMContentLoaded', loadLiveReadings);
    </script>
    """

    # CSS styling
    css = """
    <style>
        * {
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: #0f172a;
            color: #e2e8f0;
        }

        h1 {
            margin: 0 0 24px 0;
            font-size: 28px;
            font-weight: 600;
            color: #f1f5f9;
        }

        .section-title {
            margin: 0 0 16px 0;
            font-size: 18px;
            font-weight: 600;
            color: #f1f5f9;
        }

        .status-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }

        .card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 16px;
        }

        .card-label {
            font-size: 13px;
            color: #94a3b8;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .card-value {
            font-size: 18px;
            font-weight: 600;
            color: #f1f5f9;
            word-break: break-all;
        }

        .live-readings {
            margin-bottom: 24px;
        }

        .loading {
            color: #94a3b8;
            font-size: 14px;
            padding: 20px 0;
            text-align: center;
        }

        .readings-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
        }

        .reading-item {
            background: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 6px;
            padding: 12px;
        }

        .reading-label {
            font-size: 12px;
            color: #94a3b8;
            margin-bottom: 6px;
            font-weight: 500;
        }

        .reading-value {
            font-size: 20px;
            font-weight: 600;
            color: #f1f5f9;
        }

        .value-missing {
            color: #64748b;
        }

        .value-present {
            color: #10b981;
        }

        .estimated {
            font-size: 11px;
            color: #fbbf24;
            font-weight: 400;
            margin-left: 4px;
        }

        .warning-banner {
            background: #451a03;
            border: 1px solid #92400e;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 24px;
            color: #fbbf24;
            font-size: 14px;
        }

        .warning-banner code {
            background: #78350f;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 13px;
        }

        .actions-section {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 24px;
        }

        .actions-buttons {
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }

        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-primary {
            background: #3b82f6;
            color: white;
        }

        .btn-primary:hover {
            background: #2563eb;
        }

        .btn-secondary {
            background: #475569;
            color: #e2e8f0;
        }

        .btn-secondary:hover {
            background: #334155;
        }

        .actions-help {
            border-top: 1px solid #334155;
            padding-top: 16px;
        }

        .help-item {
            margin: 12px 0;
            font-size: 13px;
            color: #cbd5e1;
            line-height: 1.6;
        }

        .help-item strong {
            color: #f1f5f9;
            display: block;
            margin-bottom: 4px;
        }

        .chart-card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 24px;
        }

        .plotly-graph-div {
            background: white !important;
            border-radius: 4px;
        }
    </style>
    """

    # Assemble HTML
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>EnergyHome Forecast</title>
        {css}
        <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    </head>
    <body>
        <h1>⚡ EnergyHome Forecast</h1>

        {status_cards}

        {live_readings}

        {grid_warning}

        {action_buttons}

        <div class="chart-card">
            {fig1.to_html(include_plotlyjs=False, full_html=False, div_id="plot1")}
        </div>

        <div class="chart-card">
            {fig2.to_html(include_plotlyjs=False, full_html=False, div_id="plot2")}
        </div>

        <div class="chart-card">
            {fig3.to_html(include_plotlyjs=False, full_html=False, div_id="plot3")}
        </div>

        {javascript}
    </body>
    </html>
    """
    return html
