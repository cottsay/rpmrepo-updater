#!/bin/bash

export PYTHONPATH=/home/rosbuild/rpmrepo_updater/src

# export dump of change
python ~/rpmrepo_updater/scripts/diff_packages.py /var/www/repos/ros/ubuntu/dists/precise/main/binary-amd64/Packages /var/www/repos/ros-shadow-fixed/ubuntu/dists/precise/main/binary-amd64/Packages groovy --output-dir ~/rpmrepo_updater/logs


python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros/ubuntu -r groovy -d oneiric -d precise -d quantal -a i386 -u file:/var/www/repos/ros-shadow-fixed/ubuntu -c
python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros/ubuntu -r groovy -d oneiric -d precise -d quantal -a amd64 -u file:/var/www/repos/ros-shadow-fixed/ubuntu -c
python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros/ubuntu -r groovy -d oneiric -d precise -d quantal -a source -u file:/var/www/repos/ros-shadow-fixed/ubuntu -c
