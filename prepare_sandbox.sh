#!/bin/bash
set -ex

if [ "$#" -ne 1 ]; then
    echo "Illegal number of parameters"
    exit 1
fi

SIZE=5M
SANDBOX_ROOT=$1

./clear_sandbox.sh $1 || true

cd $1

touch {0..9}.img
echo Creating files
for i in {0..9}; do fallocate $i.img -l $SIZE; done
echo Creating filesystems
for i in {0..9}; do mkfs.ext4 -F $i.img > /dev/null 2>&1; done

mkdir $SANDBOX_ROOT/{0..9}
echo Mounting files
for i in {0..9}; do mount $i.img $SANDBOX_ROOT/$i/ -o rw,nosuid,nodev,noexec; done
for i in {0..9}; do chown uploaded:ftp $SANDBOX_ROOT/$i/ -R; done
