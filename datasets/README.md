# Healthcare data

The realistic experiment uses the **Sepsis Cases - Event Log** published by
Felix Mannhardt through 4TU.ResearchData:

- DOI: <https://doi.org/10.4121/uuid:915d2bfb-7e84-49ad-a286-dc35f063a460>
- Dataset record: <https://data.4tu.nl/articles/_/12707639/1>
- Version: 1 (2016)
- Expected file: `Sepsis Cases - Event Log.xes.gz`
- Expected MD5: `b5671166ac71eb20680d3c74616c43d2`
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

No artificial teaching dataset is used by the current circuit or proof command.
