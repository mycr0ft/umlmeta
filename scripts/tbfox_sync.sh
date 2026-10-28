#!/bin/sh
# tbfox_sync.sh - rescues the OMG corpora from the removable SD card
# (/mnt/TBFox - Jon's tablet's card) onto local storage, then leaves
# /mnt/TBFox as a symlink to the local copy so the corpus suites run
# when the card is absent.
#
# Usage: ./scripts/tbfox_sync.sh /dev/sdXN
#   (the SD card's partition device; find it with lsblk after plugging
#    the card into a reader - typically an exFAT/FAT partition on
#    /dev/sdb1 or /dev/mmcblk0p1)
#
# Steps:
#   1. mount the card at /mnt/tbfox-card (sudo)
#   2. rsync the card content to /storage16/home/jfox/TBFox/
#   3. point /mnt/TBFox at the local copy (symlink)
#   4. unmount the card (it can go back in the tablet)
#
# After this the SD card is never needed by this box again; the
# hardcoded /mnt/TBFox/... paths in the check suites keep working.

set -eu

DEV="${1:?usage: tbfox_sync.sh /dev/sdXN  (lsblk to find the card)}"

CARD_MOUNT=/mnt/tbfox-card
LOCAL_CORPUS=/storage16/home/jfox/TBFox

sudo mkdir -p "$CARD_MOUNT"
sudo mount -o ro "$DEV" "$CARD_MOUNT"

mkdir -p "$LOCAL_CORPUS"
rsync -a --info=stats2 "$CARD_MOUNT/" "$LOCAL_CORPUS/"

# point /mnt/TBFox at the local copy
if mountpoint -q /mnt/TBFox 2>/dev/null; then
    sudo umount /mnt/TBFox
fi
if [ -d /mnt/TBFox ] && [ ! -L /mnt/TBFox ]; then
    sudo rmdir /mnt/TBFox 2>/dev/null || sudo mv /mnt/TBFox /mnt/TBFox.old
fi
sudo ln -sfn "$LOCAL_CORPUS" /mnt/TBFox

sudo umount "$CARD_MOUNT"
echo "DONE: /mnt/TBFox -> $LOCAL_CORPUS"
ls -la /mnt/TBFox/ | head