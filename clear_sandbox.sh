#!/bin/bash
set -ex

if [ "$#" -ne 1 ]; then
    echo "Illegal number of parameters"
    exit 1
fi

SANDBOX_ROOT=$1

for i in {0..9}; do umount $SANDBOX_ROOT/$i/; done
rmdir $SANDBOX_ROOT/{0..9}
rm {0..9}.img
