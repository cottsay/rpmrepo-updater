#!/bin/bash

export PYTHONPATH=/home/rosbuild/rpmrepo_updater/src

python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros-shadow-fixed/ubuntu -y /home/rosbuild/rpmrepo_updater/config/pcl.upstream.yaml -c

python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros/ubuntu -y /home/rosbuild/rpmrepo_updater/config/pcl.upstream.yaml -c


python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros-shadow-fixed/ubuntu -y /home/rosbuild/rpmrepo_updater/config/colladadom.upstream.yaml -c
python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros/ubuntu -y /home/rosbuild/rpmrepo_updater/config/colladadom.upstream.yaml -c


python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros-shadow-fixed/ubuntu -y /home/rosbuild/rpmrepo_updater/config/bullet.upstream.yaml -c
python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros/ubuntu -y /home/rosbuild/rpmrepo_updater/config/bullet.upstream.yaml -c

python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros-shadow-fixed/ubuntu -y /home/rosbuild/rpmrepo_updater/config/gazebo.upstream.yaml -c
python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros/ubuntu -y /home/rosbuild/rpmrepo_updater/config/gazebo.upstream.yaml -c

python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros-shadow-fixed/ubuntu -y /home/rosbuild/rpmrepo_updater/config/gazebo2.upstream.yaml -c
python /home/rosbuild/rpmrepo_updater/scripts/prepare_sync.py /var/www/repos/ros/ubuntu -y /home/rosbuild/rpmrepo_updater/config/gazebo2.upstream.yaml -c
