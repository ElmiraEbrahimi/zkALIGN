# Datasets

The evaluation uses four public event logs from 4TU.ResearchData.

| Dataset | Identifier | Source |
| --- | --- | --- |
| BPI Challenge 2013, Closed Problems | `bpic13cp` | [DOI](https://doi.org/10.4121/uuid:c2c3b154-ab26-4b31-a0e8-8f2350ddac11) |
| Road Traffic Fine Management Process | `rtfm` | [DOI](https://doi.org/10.4121/uuid:270fd440-1057-4fb9-89a9-b699b47990f5) |
| Sepsis Cases | `sepsis` | [DOI](https://doi.org/10.4121/uuid:915d2bfb-7e84-49ad-a286-dc35f063a460) |
| Hospital Billing | `hospital` | [DOI](https://doi.org/10.4121/uuid:76c46b83-c930-4798-a1c9-4be94dfeb741) |

After installing the project, run from the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m eval.data --download-only
```

To download selected logs, add `--datasets sepsis hospital`.
Files are saved as `datasets/raw/evaluation/<identifier>.xes.gz`, alongside
their source metadata. Downloads are checked against the source DOI, file size,
and project-local MiMC fingerprints in [sources.lock.json](../eval/sources.lock.json).

The source records specify each dataset's authors, version, and terms of use.
Raw logs are excluded from Git. The single-case demonstration uses a separate
Sepsis cache downloaded by `make data`.
