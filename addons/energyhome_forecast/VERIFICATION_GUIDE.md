# EnergyHome Forecast - Endpoint Verification Guide

This guide helps you verify that all API endpoints are working correctly under Home Assistant ingress.

## Prerequisites

1. Restart the EnergyHome Forecast add-on
2. Open the add-on UI in Home Assistant
3. Open browser DevTools (F12 or right-click → Inspect)

## Step 1: Verify Endpoints Exist (Server-Side)

All required endpoints are confirmed to exist in `main.py`:

✅ `@app.get("/api/status")` - line 256
✅ `@app.get("/api/history")` - line 267
✅ `@app.get("/api/forecast")` - line 272
✅ `@app.get("/api/latest")` - line 277
✅ `@app.post("/api/recompute")` - line 354
✅ `@app.post("/api/ilc/update")` - line 360
✅ `@app.post("/api/poll_now")` - line 367

## Step 2: Test GET Endpoints from Browser

From the add-on UI page, manually navigate to these URLs in the address bar:

### Test /api/status
```
./api/status
```
**Expected response:**
```json
{
  "last_poll_utc": "2026-01-10T12:15:00Z",
  "db_path": "/data/energyhome.sqlite",
  "configured_entities": {...},
  "points_stored": 1234,
  "last_ilc_update_local": "2026-01-10"
}
```

### Test /api/latest
```
./api/latest
```
**Expected response:**
```json
{
  "ts_utc": "2026-01-10T12:15:00Z",
  "signals": {
    "total_w": 1234.0,
    "l1_w": 410.0,
    "l2_w": 390.0,
    "l3_w": 434.0,
    "grid_l1_a": 3.2,
    "grid_l1_w": 736.0,
    "grid_l1_w_estimated": false,
    "soc_pct": 78.0,
    "inverter_w": 1200.0
  }
}
```

### Test /api/history
```
./api/history?hours=2
```
**Expected response:**
```json
{
  "timestamps": ["2026-01-10T10:00:00+0000", ...],
  "total_w": [1234.0, 1250.0, ...],
  "l1_w": [410.0, 415.0, ...],
  "grid_l1_w": [100.0, 105.0, ...],
  ...
}
```

### Test /api/forecast
```
./api/forecast
```
**Expected response:**
```json
{
  "timestamps": ["2026-01-10T12:00:00+0000", ...],
  "total_w": [1300.0, 1350.0, ...],
  ...
}
```

## Step 3: Test POST Endpoints from Browser Console

Open DevTools → Console tab and run these commands:

### Test /api/poll_now
```javascript
fetch('./api/poll_now', {method: 'POST'})
  .then(r => r.json())
  .then(console.log)
```
**Expected output:**
```json
{"status": "ok", "message": "Poll completed successfully"}
```

### Test /api/ilc/update
```javascript
fetch('./api/ilc/update', {method: 'POST'})
  .then(r => r.json())
  .then(console.log)
```
**Expected output:**
```json
{"status": "ok"}
```

### Test /api/recompute
```javascript
fetch('./api/recompute', {method: 'POST'})
  .then(r => r.json())
  .then(console.log)
```
**Expected output:**
```json
{"status": "ok"}
```

## Step 4: Test Using API Helpers

The UI now includes `apiGet()` and `apiPost()` helper functions. Test them from the console:

### Test apiGet
```javascript
apiGet('latest').then(console.log)
```

### Test apiPost
```javascript
apiPost('poll_now').then(console.log)
```

## Step 5: Verify UI Buttons Work

Click each button in the UI and verify:

### 📊 Poll now button
- Should show: "✅ Poll completed successfully! Reloading page..."
- Page reloads automatically
- Live readings panel updates with latest values

### 🎓 Update learning (ILC) button
- Should show: "✅ ILC update completed! Reloading page..."
- Page reloads automatically
- Status card shows updated "Last ILC Update" timestamp

### 🔄 Refresh forecast button
- Should show: "✅ Forecast refreshed! Reloading page..."
- Page reloads automatically
- Forecast plot updates with new predictions

## Step 6: Verify Live Readings Panel

On page load, the Live Readings panel should:

1. Show "Loading latest sensor values..." briefly
2. Then display a grid of sensor readings:
   - Total Load (W)
   - L1/L2/L3 Load (W)
   - Grid L1/L2/L3 Current (A) - if configured
   - Grid L1/L2/L3 Power (W) - if configured
   - Inverter Load (W) - if configured
   - Battery SOC (%) - if configured
3. Missing sensors show "—" in gray
4. Estimated values show "(est.)" in yellow

## Common Issues and Solutions

### Issue: "Failed to load live readings" with JSON error

**Check:**
1. Open DevTools → Network tab
2. Find the request to `latest`
3. Click it and check the Response tab
4. If it shows HTML instead of JSON:
   - The endpoint path is wrong (should be relative `./api/latest`)
   - Or ingress routing is broken

**Solution:**
- All fetch calls in ui.py should use `./api/...` (relative paths)
- Verify by checking ui.py:189, 334, 344, 354

### Issue: Button shows "❌ Poll failed: HTTP 404: Not Found"

**Check:**
1. Verify the endpoint exists in main.py (see Step 1)
2. Check that ui.py uses `apiPost('poll_now')` not `apiPost('/api/poll_now')`
3. Test the endpoint directly from browser console (Step 3)

**Solution:**
- The helper functions automatically add `./api/` prefix
- Use `apiPost('poll_now')` NOT `apiPost('/api/poll_now')`

### Issue: Network tab shows "Blocked by CORS policy"

**This should NOT happen with relative paths.**

If you see CORS errors:
- You're using absolute paths somewhere
- Search ui.py for `fetch('/api/` (should be `fetch('./api/`)

### Issue: Buttons do nothing / no alert appears

**Check:**
1. Open DevTools → Console tab
2. Look for JavaScript errors
3. Common causes:
   - Syntax error in ui.py JavaScript section
   - Missing closing tags in HTML

**Solution:**
- Verify ui.py syntax (especially the triple-quoted strings)
- Restart the add-on to reload the UI

## Success Criteria

✅ All GET endpoints return valid JSON when accessed via `./api/...`
✅ All POST endpoints return `{"status": "ok"}` when called from console
✅ Live readings panel loads without errors
✅ All three buttons work and show success messages
✅ No JavaScript errors in browser console
✅ No CORS errors in network tab
✅ No "Unexpected non-whitespace character" JSON errors

## Advanced Debugging

### Enable verbose error logging

Add this to the browser console to log all fetch calls:

```javascript
const originalFetch = window.fetch;
window.fetch = function(...args) {
  console.log('FETCH:', args);
  return originalFetch.apply(this, args)
    .then(r => {
      console.log('RESPONSE:', r.status, args[0]);
      return r;
    });
};
```

Then reload the page and watch the console for all API calls.

### Check backend logs

In Home Assistant:
1. Go to Settings → Add-ons
2. Click EnergyHome Forecast
3. Click the "Log" tab
4. Look for errors or warnings when calling endpoints

Common backend errors:
- `sqlite3.OperationalError: no such table` - database needs migration
- `KeyError: 'entity_id'` - entity configuration issue
- `AttributeError: 'NoneType'` - missing required field

## API Helper Functions Reference

### apiGet(path)
Makes a GET request to `./api/{path}` and returns parsed JSON.

**Usage:**
```javascript
const status = await apiGet('status');
const latest = await apiGet('latest');
const history = await apiGet('history?hours=24');
```

**Error handling:**
Throws an error with message `"HTTP {status}: {response_text}"` on failure.

### apiPost(path)
Makes a POST request to `./api/{path}` and returns parsed JSON.

**Usage:**
```javascript
await apiPost('poll_now');
await apiPost('ilc/update');
await apiPost('recompute');
```

**Error handling:**
Same as `apiGet()` - throws descriptive error on failure.

## Contact

If all tests pass but you still encounter issues, check:
- Add-on logs for backend errors
- Home Assistant logs for ingress routing issues
- Browser console for client-side JavaScript errors

Report issues at: https://github.com/josemaria1992/energyHome/issues
