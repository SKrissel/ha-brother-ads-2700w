# Brother ADS-2700W for Home Assistant

Custom integration for the **Brother ADS-2700W** document scanner. It reads the
maintenance counters from the scanner's web interface and keeps the scanner's
clock correct.

The ADS-2700W loses its time whenever it is switched off and only syncs via SNTP
once per hour. If you switch it on just for a few scans, files and e-mails get
stamped with the factory date. This integration notices when the scanner comes
online with a wrong clock and makes it sync right away.

## Features

| Entity | Description |
|---|---|
| Online | Whether the scanner is switched on and reachable |
| Status | Operating state as shown on the start page of the web interface, e.g. `Ready` or `Cover is Open` (unavailable while the scanner is off) |
| Scanned pages | Total page counter |
| Pick-up roller remaining | Remaining roller life in % (100,000 pages) and pages |
| Maintenance remaining | Remaining scheduled maintenance interval in % (5,000 pages) and pages |
| Paper jams | Total paper jams |
| Errors | Number of entries in the error history, entries as attribute |
| Pick-up roller replacements, Maintenance resets | Diagnostic counters |
| Location, Contact | As configured on the scanner (diagnostic) |
| Clock offset | Deviation of the time shown by the scanner from Home Assistant's local time (diagnostic) |
| Sync time | Button that triggers an SNTP sync |

The scanner is usually switched off, so the counters keep their last known
values while it is unreachable, also across Home Assistant restarts.

## Installation

### HACS

1. HACS → three-dot menu → **Custom repositories**
2. Add `https://github.com/SKrissel/ha-brother-ads-2700w` with category **Integration**
3. Install **Brother ADS-2700W** and restart Home Assistant

### Manual

Copy `custom_components/brother_ads_2700w` into your `config/custom_components`
folder and restart Home Assistant.

## Setup

Switch the scanner on, then go to **Settings → Devices & services → Add
integration → Brother ADS-2700W** and enter:

- **Host**: IP address or host name of the scanner
- **Administrator password**: password of the web interface. Only needed for
  the time sync; the counters can be read without it.

Host and password can be changed later via **Reconfigure**. Automatic time sync
can be switched off in the integration options.

## Time sync requirements

- An SNTP server must be configured on the scanner
  (web interface → Administrator → Date & Time → SNTP).
- The time sync saves the date settings of the scanner with the UTC offset
  currently in effect in Home Assistant's time zone (including daylight saving)
  and the 24-hour clock format. The scanner's own daylight saving switch is
  turned off, because it does not take effect on the ADS-2700W.
- The scanner is polled every 30 seconds and its displayed time is compared with
  Home Assistant's local time (the scanner reports its local time in the HTTP
  `Date` header). A sync is triggered when it is off by more than two minutes,
  which also covers a daylight saving change, at most once every five minutes.

## Icon

The integration ships its own icon in `custom_components/brother_ads_2700w/brand/`,
which Home Assistant 2026.3 and newer shows on the integration and device pages.
Older versions show the generic placeholder. The HACS repository list still loads
icons from the central brands CDN and therefore shows the placeholder for now.

## Limitations

- Only tested with the ADS-2700W (firmware M:4.28/P:3.89). Other Brother ADS
  models with the same web interface may work, feedback is welcome.
- Communication is plain HTTP, as provided by the scanner.

## Development

```sh
pip install -r requirements_test.txt
pytest
```

The tests run against a fake of the scanner's web server modelled on captured
traffic (`tests/fake_scanner.py`).

### Releasing

Bump `version` in `custom_components/brother_ads_2700w/manifest.json` and push
to `main`. Once all checks pass, the workflow creates the tag and GitHub release
for that version, which HACS uses for version numbers and update notifications.
