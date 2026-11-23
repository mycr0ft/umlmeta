#!/bin/sh
# corpus_sync.sh - copy the model corpora off a removable card (or any
# mounted directory) onto a local directory, so the corpus-dependent check
# suites find them after the card is gone.
#
# Usage: ./scripts/corpus_sync.sh /dev/sdXN [DEST]
#   (find the partition with lsblk after plugging the card into a reader;
#    typically an exFAT/FAT partition on /dev/sdb1 or /dev/mmcblk0p1)
#
# DEST defaults to $UMLMETA_CORPUS, else ~/uml-corpus.  The script copies,
# unmounts, and prints the export line to put in your shell profile; the
# suites themselves address everything by relative path under that root.
#
# Nothing here is particular to one machine: the card, the destination and
# the mount point are all arguments or environment variables.

set -eu

DEV="${1:?usage: corpus_sync.sh /dev/sdXN [DEST]  (lsblk to find the card)}"
DEST="${2:-${UMLMETA_CORPUS:-$HOME/uml-corpus}}"

CARD_MOUNT="$(mktemp -d)"
trap 'sudo umount "$CARD_MOUNT" 2>/dev/null || true; rmdir "$CARD_MOUNT" 2>/dev/null || true' EXIT

sudo mount -o ro "$DEV" "$CARD_MOUNT"
mkdir -p "$DEST"
rsync -a --info=stats2 "$CARD_MOUNT/" "$DEST/"
sudo umount "$CARD_MOUNT"

echo "Copied $DEV -> $DEST"
echo "Add to your shell profile:  export UMLMETA_CORPUS=\"$DEST\""
