#!/bin/bash

export PYTHONPATH=/home/rosbuild/rpmrepo_updater/src

# export dump of change
python ~/rpmrepo_updater/scripts/diff_packages.py /var/www/repos/ros/ubuntu/dists/precise/main/binary-amd64/Packages /var/www/repos/ros-shadow-fixed/ubuntu/dists/precise/main/binary-amd64/Packages hydro --output-dir ~/rpmrepo_updater/logs

# i386
python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros/ubuntu -r hydro -d precise -d quantal -d raring -a i386 -u file:/var/www/repos/ros-shadow-fixed/ubuntu -c
# amd64
python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros/ubuntu -r hydro -d precise -d quantal -d raring -a amd64 -u file:/var/www/repos/ros-shadow-fixed/ubuntu -c
# source
python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros/ubuntu -r hydro -d precise -d quantal -d raring -a source -u file:/var/www/repos/ros-shadow-fixed/ubuntu -c
