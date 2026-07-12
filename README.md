# Zcash Shielded Observatory

Zcash Shielded Observatory is an evidence-led dashboard following the transition of Zcash shielded supply from Sapling and Orchard into the Ironwood era. Ironwood activates with NU6.3 on Mainnet at block `3,428,143`.

The navigation uses the official Zcash brandmark from the Zcash Media Kit. The concentric-ring Ironwood identifier is an original dashboard illustration, not an official Ironwood logo.

The project is derived from **Orchard Integrity Monitor** and keeps its central principle: public value-pool accounting can show balances and net changes, but it cannot prove the private route or destination of individual funds.

## Architecture

The published site remains static and GitHub Pages compatible:

```text
ZcashInfo ───────────────┐
                        ├─ scripts/update.py ─ data/data.json ─ GitHub Pages
Zebra RPC (optional) ────┘                    └ data/ironwood-history.json
```

- ZcashInfo supplies public current balances, chain height, and historical snapshots.
- Zebra 6.0.0+ is the primary Ironwood source when `ZEBRA_RPC_URL` is configured in GitHub Actions secrets.
- The browser never contacts Zebra and never receives RPC credentials.
- GitHub Actions refreshes the versioned dataset hourly.
- All monetary values are stored as integer zatoshi.

## Ironwood state machine

The collector publishes one of:

- `pending_activation`
- `supported_pre_activation`
- `activation_reached_waiting_data`
- `backfilling`
- `active`
- `stale`
- `source_error`

Discovery uses `getblockchaininfo.valuePools[].id === "ironwood"`; array position and non-zero balance are never used as capability signals. `z_gettreestate(-1).ironwood` is an additional activation signal.

## Automatic backfill

Once a configured Zebra node reports a monitored Ironwood pool at or after activation, the collector calls `getblock(height, 1)` from block `3,428,143` through the current tip. Each record stores height, block hash, timestamp, `chainValueZat`, and `valueDeltaZat` when available.

The backfill is resumable and idempotent: existing heights are keyed and replaced rather than duplicated. On each run the collector re-fetches the last 12 stored block hashes; a mismatch truncates that block and every descendant before collection resumes. `data/ironwood-history.json` is committed only after an atomic write.

## Data semantics

“Shielded supply” includes Sprout, Sapling, Orchard, and Ironwood. Sprout is retained for correct accounting but deliberately de-emphasized in the interface. Lockbox is included in total pool integrity, not in shielded supply.

Snapshot differences and `valueDeltaZat` are **net value-pool changes**. They are not gross inflow/outflow and do not establish that an Orchard decrease entered Ironwood.

## Configuration

The public dashboard works before Ironwood activation without Zebra and displays `Pending activation`. For automatic Ironwood collection, add repository secrets:

```text
ZEBRA_RPC_URL
ZEBRA_RPC_USER       # optional if the endpoint uses another trusted auth layer
ZEBRA_RPC_PASSWORD   # optional
```

Do not expose Zebra RPC directly to the browser or commit credentials. Zebra RPC is security-sensitive and should normally be private/authenticated.

## Local development

```bash
python3 scripts/update.py
python3 -m unittest discover -s tests -v
python3 -m http.server 8000
```

Open `http://localhost:8000`.

## Sources and limitations

- [ZcashInfo API](https://api.zcashinfo.com/docs)
- [Zebra documentation](https://zebra.zfnd.org/)
- [Zebra 6.0.0 release](https://forum.zcashcommunity.com/t/zebra-6-0-0-release/56607)

No stable official public Zebra RPC endpoint is assumed. ZcashInfo is a public third-party source; the interface reports freshness and source readiness rather than silently fabricating missing Ironwood data.
