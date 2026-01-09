from __future__ import annotations

from typing import Dict, List

import plotly.graph_objects as go
from plotly.subplots import make_subplots


def render_dashboard(
    history: Dict[str, List],
    forecast: Dict[str, List],
    status: Dict[str, str | int],
) -> str:
    history_times = history.get("timestamps", [])
    forecast_times = forecast.get("timestamps", [])

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08)

    fig.add_trace(
        go.Scatter(x=history_times, y=history.get("total_w", []), name="Total Actual"),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=forecast_times, y=forecast.get("total_w", []), name="Total Forecast"),
        row=1,
        col=1,
    )

    for phase in ["l1_w", "l2_w", "l3_w"]:
        fig.add_trace(
            go.Scatter(
                x=history_times,
                y=history.get(phase, []),
                name=f"{phase.upper()} Actual",
            ),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=forecast_times,
                y=forecast.get(phase, []),
                name=f"{phase.upper()} Forecast",
            ),
            row=2,
            col=1,
        )

    imbalance = []
    for l1, l2, l3 in zip(
        history.get("l1_w", []), history.get("l2_w", []), history.get("l3_w", [])
    ):
        if l1 is None or l2 is None or l3 is None:
            imbalance.append(None)
        else:
            imbalance.append(max(l1, l2, l3) - min(l1, l2, l3))

    fig.add_trace(
        go.Scatter(x=history_times, y=imbalance, name="Phase Imbalance"),
        row=3,
        col=1,
    )

    fig.update_layout(height=900, showlegend=True, margin=dict(t=40, l=40, r=40, b=40))

    status_block = """
    <div class=\"status\">
      <div><strong>Last poll:</strong> {last_poll}</div>
      <div><strong>Points stored:</strong> {points}</div>
      <div><strong>Last ILC update:</strong> {ilc}</div>
    </div>
    """.format(
        last_poll=status.get("last_poll_utc", "n/a"),
        points=status.get("points_stored", 0),
        ilc=status.get("last_ilc_update_local", "n/a"),
    )

    buttons = """
    <div class=\"actions\">
      <button onclick=\"fetch('/api/recompute', {method: 'POST'}).then(() => location.reload())\">Recompute forecast</button>
      <button onclick=\"fetch('/api/ilc/update', {method: 'POST'}).then(() => location.reload())\">Force ILC update</button>
    </div>
    """

    html = f"""
    <html>
      <head>
        <title>EnergyHome Forecast</title>
        <style>
          body {{ font-family: sans-serif; margin: 16px; }}
          .status {{ margin-bottom: 12px; }}
          .actions button {{ margin-right: 8px; padding: 6px 12px; }}
        </style>
      </head>
      <body>
        <h1>EnergyHome Forecast</h1>
        {status_block}
        {buttons}
        {fig.to_html(include_plotlyjs='cdn', full_html=False)}
      </body>
    </html>
    """
    return html
