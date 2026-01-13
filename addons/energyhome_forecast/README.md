# EnergyHome Forecast Add-on

Collects inverter load data from Home Assistant and serves 48-hour forecasts with iterative learning correction plus a simple UI.

## What it does

- Polls Home Assistant sensor entities every 15 minutes using the Supervisor token by default.
- Stores measurements in SQLite and builds a 48h forecast for total load and each phase.
- Exposes a Plotly dashboard at `/ui` via Home Assistant ingress.

## Logs

Open the add-on in Home Assistant and select the **Log** tab to view runtime output.
