# Development Tools

## import_sample_csv.py

Import sample data into the EnergyHome Forecast database for testing and development.

### Quick Start

1. **Generate sample data:**
   ```bash
   python import_sample_csv.py --generate-sample
   ```

   This creates `sample_data.csv` with 7 days of synthetic 15-minute interval data.

2. **Import into database:**
   ```bash
   python import_sample_csv.py /data/energyhome.sqlite sample_data.csv
   ```

3. **Update ILC and forecast:**
   ```bash
   curl -X POST http://localhost:8080/api/ilc/update
   curl -X POST http://localhost:8080/api/recompute
   ```

4. **View in UI:**
   Open http://localhost:8080/ui

### CSV Format

The CSV must have these columns (in any order):

```
ts_local_bin_start,total_w,l1_w,l2_w,l3_w,grid_l1_w,grid_l2_w,grid_l3_w,inverter_w
```

Example row:
```
2026-01-10T14:00:00,3500.0,1200.0,1150.0,1150.0,100.0,50.0,50.0,3400.0
```

- Timestamps should be in local time (matching your configured timezone)
- Use `null` or empty string for missing values
- Power values are in Watts (W)

### Use Cases

- **Development:** Test UI changes without waiting for real data
- **Algorithm tuning:** Import known patterns to test ILC behavior
- **Debugging:** Reproduce specific scenarios
- **Demos:** Show the system with realistic data

### Notes

- The script uses `INSERT OR REPLACE`, so existing data for the same timestamp will be overwritten
- The database must exist (run the add-on at least once first)
- After import, remember to trigger ILC update and forecast recompute
