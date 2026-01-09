# energyHome

## Home Assistant Add-on Repository

This repository includes the EnergyHome Forecast Home Assistant add-on, which uses the Supervisor token by default.

### Add the repository in Home Assistant

1. In Home Assistant, go to **Settings** → **Add-ons** → **Add-on Store**.
2. Open the menu (⋮) and select **Repositories**.
3. Add this repository URL:

```
https://github.com/josemaria1992/energyHome
```

4. Find **EnergyHome Forecast** in the add-on store and click **Install**.
5. Configure the add-on, start it, and open the **Ingress** link to view the dashboard.

### How to test

With the add-on running, validate the service endpoints:

```
curl http://localhost:8080/health
curl http://localhost:8080/api/forecast
```

Then open the `/ui` dashboard via ingress in Home Assistant.

### Local build (optional)

```
./scripts/build-addon.sh
```
