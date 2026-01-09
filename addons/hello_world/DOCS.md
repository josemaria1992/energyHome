# EnergyHome Forecast Add-on

This add-on collects inverter load data from Home Assistant and serves a 48-hour forecast with iterative learning correction (ILC).

## Configuration

Set the Home Assistant URL, long-lived access token, and sensor entities.

Example configuration:

```yaml
ha_url: http://homeassistant.local:8123
ha_token: "YOUR_LONG_LIVED_TOKEN"
poll_interval_minutes: 15
timezone: Europe/Stockholm
horizon_hours: 48
entities:
  total_load_power: sensor.inverter_load_power
  l1_load_power: sensor.inverter_load_l1_power
  l2_load_power: sensor.inverter_load_l2_power
  l3_load_power: sensor.inverter_load_l3_power
  soc: sensor.inverter_battery
  grid_l1_current: sensor.inverter_grid_l1_current
  grid_l2_current: sensor.inverter_grid_l2_current
  grid_l3_current: sensor.inverter_grid_l3_current
```

## Usage

1. Install the add-on from the energyHome add-on repository.
2. Configure the Home Assistant URL and token.
3. Start the add-on.
4. Open the **Ingress** link to view the dashboard.

## Validation

Run these checks from another machine on the same network (replace the host if needed):

```
curl http://homeassistant.local:8123/api/hassio/addons/energyhome_forecast/info
curl http://homeassistant.local:8123/api/hassio/addons/energyhome_forecast/logs
```

Inside the add-on container you can also validate:

```
curl http://localhost:8080/health
curl http://localhost:8080/api/forecast
```

## Troubleshooting

- Ensure the long-lived token has permission to read the sensor entities.
- If entities are `unknown` or `unavailable`, the forecast will fall back to recent averages.
- Confirm the timezone matches your Home Assistant instance.
