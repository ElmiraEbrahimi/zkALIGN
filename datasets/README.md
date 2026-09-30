# Healthcare data

The realistic experiment uses the **Sepsis Cases - Event Log** published by
Felix Mannhardt through 4TU.ResearchData:

- DOI: <https://doi.org/10.4121/uuid:915d2bfb-7e84-49ad-a286-dc35f063a460>
- Dataset record: <https://data.4tu.nl/articles/_/12707639/1>
- Version: 1 (2016)
- Expected file: `Sepsis Cases - Event Log.xes.gz`
- Expected project-local MiMC fingerprint: `2609148250783286284f49dc67220f63465834e094537a61537001312044c01f`
- Terms: 4TU General Terms of Use, as listed on the dataset record

It is a real hospital event log with anonymized values. One case represents one
patient's hospital pathway. The record describes roughly 1,000 cases, 15,000
events, and 16 activities. Timestamps were randomized while durations within a
trace were preserved.

Download and verify it with:

```bash
python3 scripts/download_sepsis.py
```

The downloaded data is intentionally ignored by Git. This repository records
its source, version, and checksum instead of silently redistributing it.

The MiMC pin is computed with zkALIGN's length-framed `zkALIGN:file:v2`
encoding. It is a project-local fingerprint, not a checksum published by 4TU.
During migration the source file was first checked against its previously
recorded publisher MD5 `b5671166ac71eb20680d3c74616c43d2`, then its MiMC
fingerprint was computed using the Go implementation and checked in Python.
The download script now verifies MiMC only.

No artificial teaching dataset is used by the current circuit or proof command.
