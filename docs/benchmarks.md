# Benchmarks

`python bench/run.py` builds a synthetic case where each new mule account is paid from one of the twenty most recent ones, then links it and runs one chain scenario. Measured on 2026-11-16 on an 8-vCPU Linux VM with CPython 3.13:

| legs | link | simulate |
|---|---|---|
| 500 | under 0.01 s | under 0.01 s |
| 2,000 | 0.03 s | 0.01 s |
| 10,000 | under 1 s | under 0.1 s |

Real cases are tens to hundreds of legs. The pass-through search looks at every outflow of the receiving holder inside the window, so a single account with tens of thousands of outflows a day (an exchange omnibus account) will be slow and, more to the point, will produce meaningless inferred links. Leave such accounts out or cut the window.
