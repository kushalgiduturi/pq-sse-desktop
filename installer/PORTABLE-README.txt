PQ-SSE Desktop @VERSION@, portable, @VARIANT@ build
==========================================================

This folder is the whole program. Nothing needs to be installed and no admin rights
are needed.

HOW TO RUN
  1. Unzip the whole folder somewhere you can write to, for example your Documents
     folder. Do not run it from inside the zip file.
  2. Double-click  PQ-SSE-Desktop.exe
  3. On the welcome screen choose "Start the guided lesson".

Keep PQ-SSE-Desktop.exe and the folder _internal together. The program does not work
if one of them is moved away from the other.

IF WINDOWS SHOWS "Windows protected your PC"
  The program is not code signed. Click "More info", then "Run anyway".
  docs\DISTRIBUTION.md explains why this appears and how to check that your download
  is the real one (SHA-256 checksum).

WHERE YOUR DATA IS STORED
  Not in this folder. Everything the program saves goes to
      %LOCALAPPDATA%\PQ-SSE-Desktop
  (paste that line into the address bar of File Explorer to open it, or use
  Help > Open data folder inside the program). It holds your encrypted keys, the
  databases, settings and log files (in the sub-folder logs).

HOW TO REMOVE IT
  1. Close the program.
  2. Delete this folder.
  3. If you also want to delete your data, delete the folder
     %LOCALAPPDATA%\PQ-SSE-Desktop
     This cannot be undone. Keep it if you plan to use the program again.

WHICH BUILD IS THIS
@VARIANT_NOTE@

  Help > About shows the version and whether a graphics chip is in use.

WHAT THIS PROGRAM IS, AND IS NOT
  It is research and teaching software: search encrypted documents through an
  untrusted cloud, with post-quantum keys. It has not been audited by security
  experts. Do not use it to protect real records.

MORE
  docs\INSTALL.md       install, update, uninstall, troubleshooting
  docs\START_HERE.md    a five minute introduction
  LICENSE.txt and THIRD-PARTY-LICENSES.txt
