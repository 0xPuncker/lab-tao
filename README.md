# val-bittensor

Validator learning workbench — a Kubernetes-deployed Bittensor validator built on the opentensor subnet template. Used to learn and test validator ops, incentive strategy, and emission mechanics on testnet.

> Upstream: [opentensor/bittensor-subnet-template](https://github.com/opentensor/bittensor-subnet-template)  
> Docs: [docs.learnbittensor.org](https://docs.learnbittensor.org)

---

## Bittensor TL;DR

### The Network

Bittensor is a decentralized protocol that creates a marketplace for digital commodities — AI compute, data, inference, storage, etc. Participants are incentivized with **TAO**, the native token, based on the value they contribute to the network.

### TAO and Alpha

| Token | What it is |
|-------|-----------|
| **TAO (τ)** | The root token. Staked by validators, distributed by Yuma Consensus, tradeable. |
| **Alpha (α)** | Subnet-specific token introduced in dTAO. Each subnet has its own Alpha token. Validators and miners earn Alpha; Alpha can be exchanged back to TAO. |

Emissions flow: each block mints TAO → distributed to subnets proportional to stake → split between validators and miners within each subnet.

### Subnets

A **subnet** (netuid) is a self-contained market with its own incentive mechanism. Think of it as a competition arena:

- Subnet owner defines what "good work" looks like (the protocol)
- Miners compete to produce that work
- Validators assess the miners and set weights
- Yuma Consensus converts those weights into TAO/Alpha emissions

There are 64 subnets on mainnet. Testnet has separate netuids for development.

### Roles

```
Coldkey (wallet root, offline)
└── Hotkey (signs daily operations, registered on-chain)
    ├── Validator — queries miners, sets weights, earns emissions
    └── Miner — serves responses, scored by validators
```

| Role | Responsibility | Earns |
|------|---------------|-------|
| **Validator** | Queries miners, scores responses, sets weights on-chain | ~41% of subnet emissions |
| **Miner** | Responds to validator queries with useful work | ~41% of subnet emissions |
| **Subnet owner** | Designs the incentive mechanism, registers the subnet | ~18% of subnet emissions |

### Keys

- **Coldkey**: Root wallet key. Holds TAO. Never goes online. Used for registration and fund transfers.
- **Hotkey**: Day-to-day key. Registered on-chain per subnet. Signs weight transactions and axon serving.
- **Child hotkeys**: A validator can delegate their stake to child hotkeys — useful for running multiple validator instances or separating signing duties.

### Metagraph

The **metagraph** is the on-chain snapshot of a subnet's state: all registered hotkeys, their axon endpoints, stake amounts, and the most recent weights. Validators sync the metagraph each epoch to discover miners and check network state.

```python
import bittensor as bt
meta = bt.metagraph(netuid=1, network="test")
# meta.hotkeys, meta.axons, meta.stake, meta.weights
```

### Weights and Yuma Consensus

Each validator assigns weights `[0.0, 1.0]` to miners based on response quality. **Yuma Consensus** aggregates all validator weight vectors (weighted by validator stake) to produce a canonical ranking. That ranking determines how emissions are split among miners each epoch.

Key property: a single validator can't manipulate rankings unless they control enough stake to override the consensus.

### Axon and Dendrite

- **Axon**: The miner's server. Listens for incoming queries, serves responses.
- **Dendrite**: The validator's client. Sends queries to miner axons, collects responses, applies a timeout.

```
Validator (Dendrite) ──query──► Miner (Axon)
                     ◄─response─
```

### Epoch Timing

| Event | Typical frequency |
|-------|------------------|
| Block time | ~12 seconds |
| Weight-setting (tempo) | Every ~360 blocks (~72 min) |
| Metagraph resync | Every ~100 blocks (~20 min) |

---

## This Repo

### Components

| Component | What it does |
|-----------|-------------|
| `neurons/validator.py` | Validator neuron — queries miners, scores responses, sets weights |
| `neurons/miner.py` | Miner neuron — serves Dummy protocol responses |
| `strategy/scheduler.py` | Strategy scheduler — runs automated weight/economics decisions on a cron |
| `template/` | Base protocol, reward logic, utilities |
| `helm-charts/` | Kubernetes Helm chart for k3s/ArgoCD deployment |

### Config

Key env vars and CLI args:

```bash
# Wallet
--wallet.name testnet-validator
--wallet.hotkey default

# Subnet
--netuid 1
--subtensor.network test   # "test" | "finney" (mainnet)

# Axon
--axon.port 8091

# Validator tuning
--neuron.sample_size 10           # miners queried per step
--neuron.moving_average_alpha 0.1 # EMA smoothing for scores
```

### Deploy (k3s + ArgoCD)

```bash
# Helm lint
helm lint helm-charts/charts/val-bittensor

# Dry run
helm template bittensor-testnet helm-charts/charts/val-bittensor \
  -f helm-charts/charts/val-bittensor/values.yaml

# ArgoCD sync
argocd app sync bittensor-testnet --grpc-web
```

### Development

```bash
# Install
pip install -r requirements.txt

# Sensors
mypy --config-file mypy.ini || true
ruff check .
pytest --tb=short -q --ignore=tests/integration/

# Run validator locally (testnet)
python neurons/validator.py \
  --wallet.name testnet-validator \
  --wallet.hotkey default \
  --netuid 1 \
  --subtensor.network test \
  --logging.debug
```

### CI/CD

GitHub Actions (`.github/workflows/build-and-deploy.yaml`):
1. **sensors** — mypy, ruff, pytest, pip-audit, bandit, detect-secrets
2. **build** — Docker image → GHCR (`ghcr.io/0xpuncker/val-bittensor:<branch>-<sha>`)
3. **update_k8s_manifests** — rewrites `k8s/bittensor-testnet.yaml` image tag → triggers ArgoCD auto-sync

---

## References

- [Bittensor docs](https://docs.bittensor.com)
- [Learn Bittensor](https://docs.learnbittensor.org)
- [Yuma Consensus whitepaper](https://bittensor.com/whitepaper)
- [Taostats explorer](https://taostats.io)
- [opentensor/bittensor](https://github.com/opentensor/bittensor)

## License

MIT — see [LICENSE](LICENSE)
