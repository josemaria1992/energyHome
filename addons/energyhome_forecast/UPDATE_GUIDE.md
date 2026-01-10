# EnergyHome Forecast - Update & Data Persistence Guide

This guide explains how to safely update the add-on and ensure your historical data is preserved.

## Quick Facts

✅ **Your data is safe during updates** - The database is stored in `/data/energyhome.sqlite`, which persists across updates and restarts.

✅ **Updates don't require uninstalling** - Home Assistant can update add-ons in-place when you bump the version.

✅ **You can backup your database** - Use the `/api/export_db` endpoint before major changes.

## How Updates Work

### Version-Based Updates

Home Assistant Supervisor uses the `version` field in `config.yaml` to detect if an update is available.

**Current version:** `0.3.0`

When you push changes to GitHub:
1. Bump the version in `config.yaml` (e.g., `0.3.0` → `0.3.1`)
2. Commit and push to GitHub
3. In Home Assistant: Settings → Add-ons → Add-on Store
4. Click the overflow menu (⋮) → "Check for updates"
5. Update the add-on (data is preserved automatically)

### Why "Rebuild" Doesn't Always Use Latest Code

The "Rebuild" button in Home Assistant rebuilds the Docker image, but Docker aggressively caches layers. If the version doesn't change, Docker may reuse cached layers even if GitHub has new code.

**Solution:** Always bump the version number when pushing changes.

### Cache-Buster Mechanism

The Dockerfile includes a cache-busting ARG:

```dockerfile
ARG CACHEBUST=1
RUN echo "Build cache-bust: ${CACHEBUST}"
```

This helps force layer invalidation when combined with version bumps.

## Data Persistence

### Database Location

The SQLite database is stored at:
```
/data/energyhome.sqlite
```

The `/data` directory in Home Assistant add-ons is:
- ✅ Persistent across restarts
- ✅ Persistent across updates
- ✅ Persistent across rebuilds
- ❌ **Deleted on uninstall** (unless you backup first)

### What's Stored in the Database

The database contains:
- **Measurements table:** Raw sensor readings from Home Assistant
- **Binned table:** 15-minute aggregated data (total_w, l1_w, l2_w, l3_w, grid power, inverter, etc.)
- **ILC curve table:** Iterative Learning Control correction curves
- **Metadata table:** Last poll timestamp, last ILC update, etc.

### Verifying Database Location

On startup, check the logs for:
```
[INFO] EnergyHome Forecast v0.3.0 starting...
[INFO] Database path: /data/energyhome.sqlite
[INFO] Polling interval: 15 minutes
[INFO] Timezone: Europe/Stockholm
[INFO] Forecast horizon: 48 hours
```

If you see a different path (e.g., `/app/energyhome.sqlite`), **your data will be lost on restart**!

## Backup Your Database

### Method 1: Download via API

Navigate to:
```
http://your-ha-url/api/energyhome-forecast/api/export_db
```

This downloads `energyhome_backup.sqlite` to your computer.

### Method 2: Use Home Assistant File Editor

1. Install "File Editor" add-on (if not already installed)
2. Navigate to `/data/energyhome_forecast/`
3. Find `energyhome.sqlite`
4. Download using the File Editor

### Method 3: SSH/Terminal Access

```bash
cp /data/energyhome.sqlite /backup/energyhome_$(date +%Y%m%d).sqlite
```

### When to Backup

Recommended before:
- Major version updates (e.g., 0.3.x → 0.4.0)
- Uninstalling the add-on
- Making schema changes
- Restoring Home Assistant from snapshot

## Update Workflow (Recommended)

1. **Backup your database:**
   ```
   ./api/export_db
   ```

2. **Check current version:**
   ```
   Settings → Add-ons → EnergyHome Forecast
   ```
   Note the current version number.

3. **Make code changes locally and test**

4. **Bump version in `config.yaml`:**
   ```yaml
   version: "0.3.1"  # Increment patch version
   ```

5. **Update version string in `run.sh`:**
   ```bash
   bashio::log.info "Starting EnergyHome Forecast add-on v0.3.1"
   ```

6. **Update version string in `main.py` startup logging:**
   ```python
   logger.info("EnergyHome Forecast v0.3.1 starting...")
   ```

7. **Commit and push to GitHub:**
   ```bash
   git add -A
   git commit -m "Bump version to 0.3.1 - <description of changes>"
   git push
   ```

8. **Update in Home Assistant:**
   - Settings → Add-ons → Add-on Store
   - Click ⋮ → "Check for updates"
   - Find EnergyHome Forecast → "Update"
   - Wait for build to complete
   - Restart add-on

9. **Verify data is preserved:**
   ```
   ./api/status
   ```
   Check `points_stored` - should match before update.

## Versioning Strategy

Use [Semantic Versioning](https://semver.org/):

- **Patch** (0.3.0 → 0.3.1): Bug fixes, minor improvements, no breaking changes
- **Minor** (0.3.0 → 0.4.0): New features, no breaking changes
- **Major** (0.3.0 → 1.0.0): Breaking changes (schema changes, API changes)

## Troubleshooting

### Problem: Data Lost After Update

**Symptoms:**
- `points_stored` is 0 after update
- Live readings show "—" for all values
- Forecast is flat/empty

**Diagnosis:**
1. Check add-on logs for database path:
   ```
   [INFO] Database path: /data/energyhome.sqlite
   ```

2. Check if database file exists:
   ```bash
   ls -lh /data/energyhome.sqlite
   ```

**Causes:**
1. Database was stored outside `/data` (old code bug)
2. Add-on was uninstalled instead of updated
3. `/data` directory was manually deleted

**Solutions:**
1. Restore from backup (if available)
2. If no backup: start fresh, data will accumulate again
3. Verify database path in logs going forward

### Problem: Update Not Detected by Home Assistant

**Symptoms:**
- Pushed new code to GitHub
- "Check for updates" shows no updates
- Version number hasn't changed in UI

**Diagnosis:**
Check `config.yaml` version field.

**Solution:**
Bump the version number:
```yaml
version: "0.3.1"  # Must be higher than current
```

### Problem: Rebuild Uses Old Code

**Symptoms:**
- Clicked "Rebuild" button
- Code hasn't changed (verified by checking logs/behavior)
- GitHub has newer commits

**Cause:**
Docker layer caching is reusing old cached layers.

**Solutions:**

1. **Preferred:** Bump version and update (not rebuild):
   - Increment `version` in `config.yaml`
   - Commit and push
   - Use "Update" not "Rebuild"

2. **Nuclear option:** Uninstall and reinstall
   - ⚠️ **WARNING: This deletes `/data`! Backup first!**
   - Backup database: `./api/export_db`
   - Uninstall add-on
   - Clear browser cache
   - Reinstall add-on
   - Restore database (manual process)

3. **Advanced:** Prune Docker builder cache
   - SSH into Home Assistant OS
   - `docker builder prune -a`
   - Rebuild add-on

### Problem: Database Schema Migration Fails

**Symptoms:**
```
[ERROR] sqlite3.OperationalError: no such column: grid_l1_w
```

**Cause:**
Database was created with old schema, migration didn't run.

**Solution:**
The storage.py `init_db()` function includes automatic migrations:

```python
# Migration: Add new columns for existing databases
cursor = conn.execute("PRAGMA table_info(binned)")
columns = [row[1] for row in cursor.fetchall()]
if "grid_l1_w" not in columns:
    conn.execute("ALTER TABLE binned ADD COLUMN grid_l1_w REAL")
...
```

If migration fails:
1. Check add-on logs for specific error
2. Backup database: `./api/export_db`
3. Manually add missing columns (advanced users):
   ```sql
   ALTER TABLE binned ADD COLUMN grid_l1_w REAL;
   ALTER TABLE binned ADD COLUMN grid_l2_w REAL;
   ALTER TABLE binned ADD COLUMN grid_l3_w REAL;
   ```
4. Or start fresh: delete `/data/energyhome.sqlite`, restart add-on

### Problem: "Rebuild" vs "Update" - Which to Use?

**Use "Update"** when:
- ✅ New version available in add-on store
- ✅ You bumped version and pushed to GitHub
- ✅ You want to preserve data (automatic)

**Use "Rebuild"** when:
- ⚠️ Testing code changes locally
- ⚠️ Forcing cache invalidation (usually not needed)
- ⚠️ Troubleshooting Docker layer issues

**Never use "Uninstall"** unless:
- ❌ Starting completely fresh
- ❌ You have a backup and want to restore clean
- ❌ Removing the add-on permanently

## Docker Layer Optimization

The Dockerfile is optimized for efficient caching:

```dockerfile
# 1. Base image (cached until Supervisor updates base images)
FROM $BUILD_FROM

# 2. Cache-buster (forces rebuild when version changes)
ARG CACHEBUST=1
RUN echo "Build cache-bust: ${CACHEBUST}"

# 3. System packages (cached until apk packages update)
RUN apk add --no-cache python3 py3-pip

# 4. Python dependencies (cached until requirements.txt changes)
WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# 5. Application code (invalidated on ANY code change)
COPY app /app
RUN python3 -m compileall /app

# 6. Run script
COPY run.sh /run.sh
RUN chmod a+x /run.sh
```

**Key principle:** Dependencies installed before app code means code changes don't require reinstalling Python packages.

## API Endpoints Reference

### GET /api/status
Returns current add-on status including points_stored.

### GET /api/export_db
Downloads the database file as `energyhome_backup.sqlite`.

### GET /api/latest
Returns latest sensor readings (useful for verifying data collection).

### POST /api/poll_now
Immediately fetches latest sensor values from Home Assistant.

## Best Practices

1. **Always bump version on changes**
   - Even tiny changes should increment patch version
   - This ensures Home Assistant detects updates

2. **Backup before major updates**
   - Download database via `/api/export_db`
   - Store backup in safe location

3. **Test locally before pushing**
   - Use development environment if available
   - Verify migrations work on old database

4. **Monitor logs on startup**
   - Verify database path is `/data/energyhome.sqlite`
   - Check for migration errors
   - Confirm polling starts

5. **Use "Update" not "Rebuild"**
   - "Update" respects versions and preserves data
   - "Rebuild" can cause cache confusion

6. **Never manually edit the database**
   - Use the API endpoints instead
   - Or use the sample import script for bulk data

## Support

### Check Logs

Settings → Add-ons → EnergyHome Forecast → Log tab

Look for:
- ✅ `[INFO] EnergyHome Forecast v0.3.0 starting...`
- ✅ `[INFO] Database path: /data/energyhome.sqlite`
- ❌ `[ERROR] sqlite3.OperationalError: ...`
- ❌ `[ERROR] Failed to fetch ...`

### Verify Data Persistence

```bash
# Via API
curl http://ha/api/energyhome-forecast/api/status

# Expected output
{
  "points_stored": 12345,  # Should be > 0
  "db_path": "/data/energyhome.sqlite",
  ...
}
```

### Report Issues

GitHub: https://github.com/josemaria1992/energyHome/issues

Include:
- Add-on version
- Home Assistant version
- Full add-on logs
- Steps to reproduce
- Expected vs actual behavior
