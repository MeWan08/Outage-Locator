# Architectural Decisions and Rationale

This document outlines the core architectural and technical decisions made during the development of **LumenGrid**, our AI-Powered Intelligence Console. While `ARCHITECTURE.md` details *how* the system functions, this document articulates the *why* behind those structural choices, ensuring clarity regarding tradeoffs, performance considerations, and system resilience.

## 1. Storage Backend: SQLite with WAL over PostgreSQL

While PostgreSQL is the industry standard for large-scale enterprise deployments, we intentionally elected to use SQLite in Write-Ahead Logging (WAL) mode for this specific implementation. 

**Reasoning:**
- **Deployment Resilience & Simplicity:** At our current scale (monitoring several thousand poles across a single utility subdivision), SQLite offers unparalleled operational simplicity. It entirely eliminates the risk of connection string misconfigurations, dependency race conditions (`depends_on: db`), and complex migration failures. 
- **Performance Efficacy:** With Write-Ahead Logging (WAL) enabled and our asynchronous `ingestion.py` queue implementing robust write-batching (one transaction per batch), we successfully circumvent SQLite's single-writer bottleneck. This design effortlessly achieves our throughput requirements. Should the system need to scale to monitor 30+ subdivisions simultaneously, this exact queue-and-batch architecture will transition flawlessly to a connection-pooled PostgreSQL environment.

## 2. Monolithic Containerized Architecture (Unified Frontend & API)

We structured the application as a single unified Docker container, where the FastAPI backend serves the compiled React frontend application as static files, rather than deploying separate frontend (Nginx/Node) and backend services.

**Reasoning:**
- **Infrastructure Portability:** A single container drastically simplifies deployment across modern Platform-as-a-Service (PaaS) providers, many of which are heavily optimized for single-service web deployments. 
- **Frictionless Delivery:** By compiling the React UI during the Docker build stage and binding it directly to the FastAPI server, we guarantee that the API and the UI are perfectly version-matched, eliminating CORS complexities and reverse-proxy routing overhead in constrained environments.

## 3. Communication Protocol: RESTful Polling vs. WebSockets

The control room console relies on asynchronous REST polling (every ~4s for incidents, ~15s for the map) rather than maintaining persistent WebSocket connections.

**Reasoning:**
- **Network Reliability & Proxy Constraints:** WebSockets frequently encounter silent failures when deployed behind aggressive load balancers, corporate firewalls, or strict reverse proxies. 
- **Overhead vs. Benefit:** Given our scale (monitoring a few thousand nodes) and the relatively small JSON payload sizes, the overhead of polling is mathematically trivial. It guarantees absolute reliability and statelessness, prioritizing a robust operator experience over unnecessary technical complexity.

## 4. Transparent Confidence Scoring vs. Opaque ML Modeling

Confidence scores for detected faults are calculated deterministically through an additive scoring engine. Every penalty factor (e.g., *inferred topology*, *no-device coverage gaps*, *stale reference points*) is explicitly named and surfaced to the operator in plain English.

**Reasoning:**
- **Auditable Trust:** In utility control rooms, "how confident are we, and why?" is a mission-critical question. An opaque machine learning model outputting an unexplainable probability percentage violates operator trust. 
- **Deterministic Tuning:** A hand-built, deterministic heuristic can be audited, debated, and retuned via simple configuration constants. This guarantees that operators understand exactly why a dispatch recommendation was made, preventing blind trust in systemic assumptions.

## 5. Topological Inference: Geometric MST for Unsurveyed Zones

For the ~60% of the grid lacking explicit surveyed wiring data, we infer topology dynamically using a Geometric Minimum Spanning Tree (MST) algorithm rooted at the local transformer, rather than waiting for manual surveys or attempting to train a predictive ML model.

**Reasoning:**
- **Immediate Value Extraction:** Waiting for perfect survey data is an anti-pattern. The MST algorithm utilizes available geographic coordinates to construct the most statistically probable physical layout.
- **Graceful Degradation:** Our algorithm degrades honestly. The system explicitly flags inferred spans (warning operators of `inferred topology`), ensuring that algorithmically guessed relationships are never presented with the same authority as manually verified physical surveys. 

*Future Consideration:* Once sufficient historical outage correlation data is accumulated over several months, we plan to augment this MST approach by up-weighting edges between poles that statistically fail together, organically learning the grid topology.

## 6. Zero-Dependency Geocoding

Grid coordinates are translated to PIN codes entirely in-memory. For poles lacking explicit PIN codes (~3%), the system executes a nearest-known-neighbor search within the local transformer cluster to assign the code.

**Reasoning:**
- **Air-Gapped Viability & Reliability:** Relying on external geocoding APIs introduces rate limits, network latency, and billing dependencies. By resolving locations using internal proximity clustering, the application remains fully self-sufficient and resilient to external network degradation.

## 7. AI Application: Natural Language Dispatch Summarization

The integration of Large Language Models (specifically Llama 3.3 via Groq) is strictly limited to translating structured JSON incident data into natural language dispatch notes for field crews. **The AI is explicitly prohibited from participating in the fault localization or decision-making process.**

**Reasoning:**
- **Segregation of Duties:** Fault localization is a deterministic graph traversal problem—it is fast, mathematically verifiable, and free. Injecting an LLM into the critical detection path would introduce latency, hallucination risks, and unacceptable costs.
- **High-Value Translation:** Translating verified, structured data into clear, concise, radio-ready English (e.g., *"Likely span fault between P-123 and P-124 affecting ~12 households"*) is exactly what LLMs excel at. If the AI service fails or times out, the system safely falls back to a deterministic string template, guaranteeing zero disruption to core operations.

## 8. Intentional Scope Boundaries

To ensure absolute precision and reliability in our core fault localization engine, several features were intentionally placed out-of-scope for this iteration:
- Role-Based Access Control (RBAC) and Authentication
- Predictive grid maintenance analytics
- High-Tension (HT) transmission modelling above the feeder level
- Automated crew routing optimization

**Reasoning:**
- **Core Competency Focus:** Attempting to build ancillary features would have diluted engineering focus. Our primary directive was to perfect the edge-case handling of the localization algorithm, ensuring that the system can reliably isolate faults amidst chaotic, noisy telemetry storms.

## 9. Debounce and Restoration Stability Windows

The system employs configurable delay timers: a `DEBOUNCE_SECONDS` window before a candidate fault becomes an actionable ticket, and a `RESTORATION_STABILITY_SECONDS` window before a restored pole auto-verifies as healthy.

**Reasoning:**
- **Transient Noise Filtration:** Power grids frequently experience transient voltage sags, flickering, or staggered sensor reporting during severe weather events. Without a debounce window, a single noisy reading would cause the UI to violently flap between states. These timers guarantee that the system only reacts to stable, sustained state changes, preventing ticket storms and alarm fatigue in the control room.

## 10. Honest Reporting of Silent Failures

When a pole stops sending heartbeats but lacks corroborating evidence (i.e., no live downstream signals and no confirmed-dark downstream signals), the system does not suppress the incident. Instead, it generates a low-confidence ticket explicitly citing *missing recent reports*.

**Reasoning:**
- **Transparency Over Suppression:** Suppressing uncorroborated silence would risk hiding real, localized faults simply because the affected sensor failed to transmit a final "dying gasp" signal. The most operationally responsible approach is to surface the anomaly transparently, accurately labeling its low confidence, and allowing human operators to exercise their judgment.
