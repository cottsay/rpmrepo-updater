from optparse import OptionParser

import os
import sys
import shutil

from rpmrepo_updater.helpers import \
    LockContext, update_metadata, \
    place_package, remove_dependent, remove_package

import rpminfo

parser = OptionParser()

parser.add_option("--delete-folder", dest="do_delete", action='store_true', default=False)

parser.add_option("-f", "--folder", dest="folders", action="append")

parser.add_option("-c", "--commit", dest="commit", action="store_true", default=False)
parser.add_option("--invalidate", dest="invalidate", action="store_true", default=False)

parser.add_option("--repo-path", dest="repo_path", default="/mnt/storage/repos/smd-ros-building/fedora")

(options, args) = parser.parse_args()

for f in options.folders:
    if not os.path.isdir(f):
        parser.error("Folder option must be a folder: %s" % f)

new_rpms = set()
for folder in options.folders:
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.endswith(".rpm"):
                new_rpms.add(rpminfo.read_from_rpm(os.path.join(root, file)))

if not new_rpms:
    parser.error("Folders %s doesn't contain any RPM files. %s" %
                 (options.folders, [os.listdir(f) for f in options.folders]))

lockfile = os.path.join(options.repo_path, 'lock')
pkgcache = {}

if options.commit:
    with LockContext(lockfile) as lock_c:

        # cache package lists
        pkgcache = {}

        # keep track of stale metadata
        md = set()

        # only invalidate dependencies if invalidation is asked for
        if options.invalidate:
            remove_dependent(options.repo_path, new_rpms,
                             cache=pkgcache, delayed_metadata=md)

        # invalidate this package always as we're about to upload the new one
        remove_package(options.repo_path, new_rpms,
                       cache=pkgcache, delayed_metadata=md)

        # place new package
        place_package(options.repo_path, new_rpms, delayed_metadata=md)

        # update metadata
        update_metadata(md)

        if options.do_delete:
            for folder in options.folders:
                print "Removing " + folder
                shutil.rmtree(folder)

else:
    print >>sys.stderr, "NO COMMIT OPTION\nWould have run invalidation of dependent packages, invalidation of package(s) and placement of package(s)"
