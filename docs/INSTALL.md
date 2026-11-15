# Install PQ-SSE Desktop

You do not need Python or any technical knowledge. You need a PC with 64-bit Windows 10
or Windows 11.

## 1. Which file do I download?

| You want | Take this file |
| --- | --- |
| The normal app. Works on every PC. | `PQ-SSE-Desktop-Setup-<version>.exe` |
| The app, and your PC has an NVIDIA graphics chip you want it to use | `PQ-SSE-Desktop-Setup-<version>-GPU.exe` (much bigger) |
| No installation at all, just a folder you can delete | `PQ-SSE-Desktop-<version>-portable-standard.zip` |

If you are not sure, take the first one. The GPU build does the same things; it is only
faster at one step (building a very large index), and it also works on a PC without an
NVIDIA chip, where it simply behaves like the normal app.

## 2. Install

1. Double-click the setup file.
2. Windows may show a blue box, **"Windows protected your PC"**. This is expected: the
   program is not code signed. Click **More info**, then **Run anyway**.
   ([DISTRIBUTION.md](DISTRIBUTION.md) explains why, and how to check your download.)
3. Choose **Install for me only** when asked. No admin password is needed.
4. Click through the pages: welcome, license, folder, shortcuts. The default answers are fine.
5. Leave **Launch PQ-SSE Desktop** ticked on the last page and click **Finish**.

The program is installed in `%LOCALAPPDATA%\Programs\PQ-SSE Desktop`.

## 3. Start

- Open the **Start Menu**, type `PQ-SSE`, and click **PQ-SSE Desktop**.
- On the welcome screen choose **Start the guided lesson**. It explains everything in
  about 15 minutes and uses a practice area, so you cannot break anything.

Portable zip instead: unzip the whole folder first, then double-click
`PQ-SSE-Desktop.exe` inside it. The file `PORTABLE-README.txt` in the folder says the rest.

## 4. Where is my data?

Everything the program saves is in one folder, separate from the program itself:

```
%LOCALAPPDATA%\PQ-SSE-Desktop
```

Paste that line into the address bar of File Explorer, or use **Help > Open data folder**
in the program. It holds your encrypted keys, the databases, your settings and the log
files. Keys are stored encrypted with your passphrase. A forgotten passphrase cannot be
recovered.

The installed version and the portable version use the same data folder.

## 5. Update

Download the newer setup file and run it. It finds the installed version, closes the
program if it is open, replaces the program files and keeps your data. You can also
switch between the normal build and the GPU build this way.

## 6. Uninstall

- **Settings > Apps > Installed apps**, find **PQ-SSE Desktop**, choose **Uninstall**; or
- Start Menu > **PQ-SSE Desktop** > **Uninstall PQ-SSE Desktop**.

The uninstaller removes the program and its shortcuts. Then it **asks** whether to delete
your data folder too. The default answer is **No**, because that folder holds your keys.
Your data is never deleted without asking.

Portable version: close the program and delete its folder. Delete
`%LOCALAPPDATA%\PQ-SSE-Desktop` as well only if you want your data gone.

## 7. Is the graphics chip (GPU) being used?

Look in any of these places:

- **Help > About PQ-SSE Desktop**, the line **GPU**.
- The line that starts with **Engine:** under the title (Expert Mode).
- **Settings** tab > **Run GPU self-test**: it compares the GPU results with the normal
  processor byte for byte and shows the measured speed for several batch sizes.

What you may read there:

| Text | Meaning |
| --- | --- |
| "In use" or "self-test passed" | The GPU is used for large batches. |
| "CuPy is not installed (this build has no GPU engine)" | You have the normal build. That is fine. |
| "no NVIDIA driver found" | GPU build, but no NVIDIA driver. Install the driver from nvidia.com, or just keep using the CPU. |
| "CUDA kernel could not be built" or "self-test FAILED" | The driver is probably too old: update it. Another known cause: your Windows user name contains letters outside plain English (accents, other scripts), which the NVIDIA compiler cannot handle. The app keeps working on the CPU. |

The GPU only speeds up building a large index. It does not speed up the post-quantum
steps (ML-KEM and ML-DSA). For small amounts of data it makes no visible difference.
You do **not** need the NVIDIA CUDA Toolkit. Only the normal NVIDIA driver. The GPU build
ships the CUDA 12.0 run-time compiler, for which NVIDIA states driver version 528.33 or
newer on Windows. It was tested with one driver only (610.62). If your driver is older
than that and the GPU is not used, update the driver from nvidia.com.

## 8. Troubleshooting

**The log file** is the first thing to look at, and to send if you ask for help:

```
%LOCALAPPDATA%\PQ-SSE-Desktop\logs\app.log
```

Open it with **Help > Open log folder**. It never contains passphrases or keys.

### Problem 1: Windows or my antivirus blocks the file

- Blue box "Windows protected your PC": click **More info**, then **Run anyway**.
- The antivirus removed the file or part of the program: restore it from quarantine or
  add the install folder as an exception, and check the SHA-256 checksum of your
  download first. See [DISTRIBUTION.md](DISTRIBUTION.md).

### Problem 2: I double-click and nothing opens

- Portable version: the file `PQ-SSE-Desktop.exe` must stay next to the folder
  `_internal`. Unzip the whole zip; do not drag only the exe out of it.
- Look at the log file above. If the folder `logs` does not exist at all, the program
  did not start: an antivirus is the usual reason (see problem 1).
- Install again over the existing install (section 5). Your data is kept.

### Problem 3: "The cloud server did not start" or "cannot bind port"

The cloud part of the program listens on port 8765 of this PC only (address 127.0.0.1).
If another program already uses that port, choose another one: **Settings** tab, switch
on **Show advanced**, change **Cloud port on 127.0.0.1** to for example 8790, then start
the cloud again on the Cloud tab. No firewall change is needed and Windows should not
show a firewall question, because nothing is offered to the network.

### Still stuck

Send the log file and the text from **Help > About PQ-SSE Desktop**.
