# Reproducible build comparison

Two builds of the same commit: `C:\Users\Kushal\pqsse-repro\desk-a\dist` and `C:\Users\Kushal\pqsse-repro\desk-b\dist`.

- Files in both: 2127; identical: 2126; different: 1; in one build only: 0.

| Different file | Size (bytes) | Kind of difference |
| --- | ---: | --- |
| `PQ-SSE-Desktop/PQ-SSE-Desktop.exe` | 6,651,061 | content |

Not yet reproducible. The two launchers differ in size (6,651,061 and 6,651,550 bytes) and in about 2.2 million
bytes, so the difference is in the embedded archive of compiled code, not only the header time stamps. All other
2,126 files, including the Qt and Python libraries, are identical. Finding the cause is open work (milestone 7).
