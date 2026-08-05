# Decisions

## 2026-08-05 — Artifact admitted to GPU validity

The user approved the exact official six-shard Q4_K_M artifact after disclosure
of its 19,570,785,664-byte size, Apache-2.0 licence, expected memory, and runtime
risk. All shard sizes and SHA-256 checksums passed. The first runtime probe is
Adreno OpenCL rather than CPU by explicit user request. No later stage is yet
authorized by evidence; successive narrowing remains in force.

## 2026-08-05 — Rejected at Adreno startup

The runtime correctly selected the X1-85, used Adreno-optimized kernels, and
reported 20/20 layer offload. It nevertheless remained at HTTP 503 after the
180-second harness timeout. The process continued allocating until its working
set reached 30.08 GiB and free system RAM fell to 1.88 GiB, at which point it
was terminated for safety. No generation was attempted. The candidate does not
advance to smoke, development, human review, or holdout on this hardware.
