# Testnet validation runbook

This is the M1 milestone of the [val-bittensor roadmap](../.specs/project/ROADMAP.md): the inside-out learning loop. You'll register a personal subnet on Bittensor testnet, run a validator and a miner under it, and observe the producer-side mechanics end-to-end.

It adapts the upstream [docs/running_on_testnet.md](running_on_testnet.md) with this project's specifics:
- Runtime is the **WSL Ubuntu venv** at `$HOME/val-bittensor-venv` (Python 3.11.15, bittensor 10.3.0).
- Wallet files live on the WSL side at `~/.bittensor/wallets/` — that's `$HOME/.bittensor/wallets/` on disk.
- All `btcli` and `python neurons/*` commands declared in [`.adp/harness.yaml`](../.adp/harness.yaml) under `actions:` (always-ask zone).
- An integration test (`tests/integration/test_testnet.py`, skipped by default) verifies each milestone you reach.

> 💸 marks steps that **cost test TAO** or otherwise transact on chain. Test TAO is free-ish (Discord faucet), but every chain action consumes block space and is recorded.

---

## 0. Pre-flight

Before starting, sensors must be green:

```bash
MSYS_NO_PATHCONV=1 wsl bash .adp/scripts/sensor.sh test          # 3 passed
MSYS_NO_PATHCONV=1 wsl bash .adp/scripts/sensor.sh lint          # All checks passed
MSYS_NO_PATHCONV=1 wsl bash .adp/scripts/sensor.sh audit         # No vulns (3 ignored, documented)
MSYS_NO_PATHCONV=1 wsl bash .adp/scripts/sensor.sh security      # 0 MEDIUM+
MSYS_NO_PATHCONV=1 wsl bash .adp/scripts/sensor.sh secret_scan   # baseline matches
```

If any fail, fix that before going to chain. The integration test depends on the same code paths.

---

## 1. Create three wallets

Per the upstream doc, you need **three** identities: subnet owner, validator, miner. Each gets its own coldkey (root, lockup); the validator and miner also get one hotkey each (operational, signs requests).

```bash
# Owner wallet — coldkey only. This wallet owns the subnet you create.
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli wallet new_coldkey --wallet.name owner"

# Validator wallet — coldkey + hotkey
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli wallet new_coldkey --wallet.name validator"
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli wallet new_hotkey  --wallet.name validator --wallet.hotkey default"

# Miner wallet — coldkey + hotkey
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli wallet new_coldkey --wallet.name miner"
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli wallet new_hotkey  --wallet.name miner --wallet.hotkey default"
```

Declared actions: `btcli_wallet_new_coldkey`, `btcli_wallet_new_hotkey`.

Each command prompts for:
- A **password** (keep these somewhere safe — you'll need them every time you use the wallet)
- The **mnemonic** is printed; **save it** (testnet means low real-money risk, but treat as practice for mainnet hygiene)

Verify wallets are on disk:

```bash
wsl ls -la $HOME/.bittensor/wallets/
# Expected: owner/  validator/  miner/
```

---

## 2. 💸 Get test TAO from the faucet

Testnet faucet is Discord-mediated, not automated. Per the upstream doc:

> Faucet is disabled on the testnet. Hence, if you don't have sufficient faucet tokens, ask the [Bittensor Discord community](https://discord.com/channels/799672011265015819/830068283314929684) for faucet tokens.

You need at least **100 test TAO** in the **owner** wallet for subnet creation, plus a few more for registration. Ask in `#help` or `#faucet` for ~150 test TAO total.

Verify you received it:

```bash
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli wallet overview --wallet.name owner --subtensor.network test"
```

Look for `Wallet balance: τ150.0` (or similar non-zero number) at the bottom.

---

## 3. 💸 Create your subnet (~100 test TAO)

```bash
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli subnet create --subtensor.network test --wallet.name owner"
```

Declared action: `btcli_subnet_create_test`.

Prompts:
- Wallet name (default: `owner` if you used that name above)
- Wallet password
- Confirm subnet creation: `y`

Save the **netuid** that's printed (`✅ Registered subnetwork with netuid: N`). You'll use it everywhere below — call it `<N>`.

Verify with the integration test (sets up the env then asserts metagraph loads):

```bash
BT_TESTNET_WALLET=owner BT_TESTNET_NETUID=<N> \
  wsl bash -c "$HOME/val-bittensor-venv/bin/python -m pytest tests/integration -v -k metagraph_loads"
# Expected: 1 passed
```

---

## 4. 💸 Register validator and miner hotkeys to your subnet

Each registration costs a small amount of test TAO (recycled — you get most of it back if you deregister).

```bash
# Validator hotkey
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli subnet register --netuid <N> --subtensor.network test --wallet.name validator --wallet.hotkey default"

# Miner hotkey
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli subnet register --netuid <N> --subtensor.network test --wallet.name miner --wallet.hotkey default"
```

Declared action: `btcli_subnet_register_test`.

Prompts: wallet password + confirm registration (`y`).

Verify both registrations with the integration test:

```bash
BT_TESTNET_WALLET=validator BT_TESTNET_NETUID=<N> \
  wsl bash -c "$HOME/val-bittensor-venv/bin/python -m pytest tests/integration -v -k wallet_registered"
# Expected: 1 passed (validator)

BT_TESTNET_WALLET=miner BT_TESTNET_NETUID=<N> \
  wsl bash -c "$HOME/val-bittensor-venv/bin/python -m pytest tests/integration -v -k wallet_registered"
# Expected: 1 passed (miner)
```

You can also confirm via `btcli wallet overview --wallet.name validator --subtensor.network test` — your hotkey shows up under the subnet table with a UID.

---

## 5. 💸 Run the miner (Terminal A)

The miner serves an axon and waits for validator queries. Open a dedicated terminal for it.

```bash
wsl bash -c "cd /mnt/c/Users/User/Documents/Claude/val-bittensor && $HOME/val-bittensor-venv/bin/python neurons/miner.py --netuid <N> --subtensor.network test --wallet.name miner --wallet.hotkey default --logging.debug"
```

Declared action: `run_miner_testnet`.

Expected log lines (early):
```
INFO  | Setting up bittensor objects.
INFO  | Wallet: Wallet (Name: 'miner', ...)
INFO  | Subtensor: Subtensor (network: test, ...)
INFO  | Metagraph: Metagraph(netuid:<N>, ...)
INFO  | Attaching forward function to miner axon.
INFO  | Axon created: Axon(...)
INFO  | Miner running...
```

Leave it running. The axon binds to the IP/port that the metagraph will advertise — by default, that's the miner's external IP. **For first-time WSL runs, you may need `--axon.external_ip <YOUR_PUBLIC_IP>` so the validator can reach it from outside your machine.** If the validator and miner run on the same machine (they will here), this matters less.

---

## 6. 💸 Run the validator (Terminal B)

The validator queries miners every step, scores responses, and sets weights on chain periodically (every `epoch_length` blocks; default 100, ~20 minutes on testnet).

For your first run you can disable the validator's own axon serving (skips one chain interaction) using `--neuron.axon_off`:

```bash
wsl bash -c "cd /mnt/c/Users/User/Documents/Claude/val-bittensor && $HOME/val-bittensor-venv/bin/python neurons/validator.py --netuid <N> --subtensor.network test --wallet.name validator --wallet.hotkey default --neuron.axon_off --logging.debug"
```

Declared action: `run_validator_testnet`.

Expected log progression:
```
INFO  | Setting up bittensor objects.
INFO  | Wallet: Wallet (Name: 'validator', ...)
INFO  | Subtensor: Subtensor (network: test, ...)
INFO  | Building validation weights.
INFO  | axon off, not serving ip to chain.
INFO  | Validator starting at block: <block#>
INFO  | step(0) block(<block#>)
INFO  | Received responses: [...]    ← miner replied with 2*query (toy reward)
INFO  | Scored responses: [1.0, 1.0, ...]   ← reward function returned 1.0 per response
DEBUG | Updated moving avg scores: [...]
INFO  | step(1) block(<block#>)
...
```

After ~100 blocks (≈20 min), you'll see a weight-setting attempt:
```
INFO  | resync_metagraph()
DEBUG | raw_weights ...
DEBUG | processed_weights ...
INFO  | set_weights on chain successfully!
```

That last line is the key milestone: your validator just submitted weights to testnet's Yuma Consensus.

---

## 7. Verify on chain

While the validator runs, in a third terminal check that emissions / weights are flowing:

```bash
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli wallet overview --wallet.name validator --subtensor.network test"
```

Look for:
- Your validator UID's row showing non-zero `EMISSION(ρ)` after a few epochs
- `VTRUST > 0` (validators with non-zero weights start accumulating trust)
- `VPERMIT` may show after enough stake accumulates

For the miner:
```bash
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli wallet overview --wallet.name miner --subtensor.network test"
```

Look for `INCENTIVE > 0` once your validator scores it.

---

## 8. (Optional) Get emissions flowing via root weights

Per the upstream doc, registering on the root network and setting subnet weights makes emissions actually distribute:

```bash
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli root register --subtensor.network test"
wsl bash -c "$HOME/val-bittensor-venv/bin/btcli root weights --subtensor.network test"
```

This is more about understanding the dTAO emission pathway than required for the validator to function. Skip for first pass; revisit when M3 (Alpha→TAO economics) work begins.

---

## 9. Stop and cleanup

Stop the miner and validator with `Ctrl+C` in each terminal. The validator saves state to `~/.bittensor/<wallet>/<hotkey>/netuid<N>/<neuron.name>/state.npz` so you can restart later without losing scores.

To free your subnet (and reclaim some of the 100 test TAO lock), wait for someone else to register and bump you out, OR explicitly burn the subnet — but that's a Bittensor-wide governance question, not something you reverse with one `btcli` call.

For your wallets, they remain on disk under `~/.bittensor/wallets/` until you delete them manually. Don't reuse the **same names** for mainnet — use different wallet names there, by convention.

---

## What you should have learned from this loop

By the end of one pass through this runbook:
- ✅ How registration consumes lock TAO (subnet creation = ~100 TAO; per-hotkey registration = small amount)
- ✅ How `btcli wallet overview` reports a hotkey's UID, stake, vtrust, emission, axon endpoint
- ✅ What the validator log looks like when forward → score → set_weights succeeds
- ✅ The `epoch_length` cadence — weights aren't set every step, only every `epoch_length` blocks
- ✅ The role separation: miner serves axon (no chain spend in normal operation); validator queries + scores + sets weights (chain spend on weight-setting)
- ✅ Why `--neuron.axon_off` matters for validators that don't need to receive queries (saves the chain spend of `serve_axon` on every restart)

These concepts directly inform M2 (subnet evaluator) and M3 (Alpha→TAO economics) — when you read mainnet metrics from outside, you now know what each number actually represents.

---

## Troubleshooting

**`btcli: command not found`** — the WSL venv isn't sourced. Use the full path: `$HOME/val-bittensor-venv/bin/btcli`.

**`AttributeError: module 'bittensor' has no attribute '<lower>'`** — bittensor 10 API drift; the inherited template still has a lowercase symbol somewhere. We caught most in M0 + the M1 audit; if you find a new one, file a quick fix and run the test sensor.

**Validator hangs on startup at "Setting up bittensor objects"** — usually the testnet RPC endpoint is slow or your network blocks WSS. Try a different network or wait. If it's persistent, check `https://test.finney.opentensor.ai:443` is reachable.

**`set_weights` fails with `wait_for_finalization` errors** — the validator passes `wait_for_inclusion=False, wait_for_finalization=False` (fire-and-forget). If a real failure surfaces, look at the `response.message` string the new bittensor 10 ExtrinsicResponse exposes (template/base/validator.py:281, fixed in M1 audit).

**Integration test passes locally but Validator can't connect** — the test only does `bt.Subtensor(network="test")` read-only; the Validator does much more. If the test passes but Validator fails, the new error surfaces in TASK-01 territory — re-run the audit `inspect.signature` checks.

---

## After this milestone

When you've successfully run through the runbook end-to-end and seen `set_weights on chain successfully!` at least once, M1 is done. Next: M2 — `subnet-evaluator`, where you'll write the outside-in tooling that reads mainnet's existing subnets and scores them, using the producer-side intuition you just built here.
