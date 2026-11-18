# Your keys: passphrases, backups and locking

Each role on a computer (the data owner, each receiver) keeps its private keys in its own file,
encrypted under a key made from that role's passphrase (scrypt, then AES-256-GCM per record). The
controls are in Insights, under **Keys and passphrases**.

## Change a passphrase

Enter whose keys (`owner` or the receiver's name), the current passphrase and a new one of 8 characters
or more. Every record is encrypted again under the new passphrase in one database transaction: if it
fails half way, the old passphrase still opens everything. Afterwards the old passphrase opens nothing.

## Back up and restore

**Back up keys** writes one `.pqkeys` file to the `backups` folder in the data folder. It holds the role's
private keys and its state (groups, receivers, keys of each epoch), encrypted under a separate **backup
passphrase** of 12 characters or more, with a higher scrypt cost than the everyday key file because a
backup travels.

- Keep the file offline (a USB stick in a drawer), and its passphrase somewhere else.
- **Restore keys** on another computer: choose the file, enter the backup passphrase and a new passphrase
  for the restored keys. A restore never replaces keys that already exist on that computer.
- A backup is a snapshot. A data owner who works after the backup and then restores it goes back in time
  to an older sequence number: the server then refuses that owner's next update as out of order. Make a
  fresh backup after big changes. Automatic recovery from this is future work.

## Locking

**Lock all keys now** closes every unlocked key file; they need their passphrase again. The keys also lock
by themselves after 15 minutes without an action. Change the number in the same card (0 turns it off).

## What is and is not protected

- Key files are made readable by your Windows account only. Administrators and the operating system can
  still read any file.
- When keys are locked, the app overwrites the key that decrypts the key file in memory. This is best
  effort: Python may still hold other copies of key bytes. It frees them, but does not overwrite them.
  Someone who can read this computer's memory while the keys are unlocked can take them.
- A forgotten passphrase cannot be recovered. Without a backup, that role's keys are lost.
- New private keys are stored as their 32 or 64-byte FIPS seed. Keys made by version 0.1 stay in the
  expanded form and keep working, on the slower pure Python code for private-key steps.

## Post-quantum code in use

The same card shows which post-quantum code runs: normally OpenSSL (native), with ML-KEM-512 on the pure
Python code. If it says **pure-Python fallback**, everything runs in slow code that is not constant time.
Use it only for learning, not for real data.
