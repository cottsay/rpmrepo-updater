from optparse import OptionParser

import os
import sys
import shutil

from rpmrepo_updater.helpers import \
    LockContext, delete_unreferenced,\
    run_update_command, invalidate_dependent, invalidate_package

parser = OptionParser()

parser.add_option("--delete-folder", dest="do_delete", action='store_true', default=False)

parser.add_option("-f", "--folder", dest="folders", action="append")
parser.add_option("-p", "--package", dest="package")

parser.add_option("-c", "--commit", dest="commit", action='store_true', default=False)
parser.add_option("--invalidate", dest="invalidate", action='store_true', default=False)

parser.add_option("--repo-path", dest="repo_path", default='/mnt/storage/repos/smd-ros-building')


(options, args) = parser.parse_args()


for f in options.folders:
    if not os.path.isdir(f):
        parser.error("Folder option must be a folder: %s" % f)

rpm_filenames = []
for folder in options.folders:
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.endswith(".rpm"):
                rpm_filenames.append(os.path.join(root, file))

if not rpm_filenames:
    parser.error("Folders %s doesn't contain any RPM files. %s" %
                 (options.folders, [os.listdir(f) for f in options.folders]))

lockfile = os.path.join(options.repo_path, 'lock')

if options.commit:
    with LockContext(lockfile) as lock_c:

        #invalidate and clear all first

        # only invalidate dependencies if invalidation is asked for
        for rpm in rpm_filenames:
            if options.invalidate:
                if changes.content['Architecture'] != 'source':
                    if not invalidate_dependent(options.repo_path,
                                                changes.content['Distribution'],
                                                changes.content['Architecture'],
                                                options.package):
                        sys.exit(1)

            # invalidate this package always as we're about to upload the new one
            if not invalidate_package(options.repo_path,
                                      changes.content['Distribution'],
                                      changes.content['Architecture'],
                                      options.package):
                sys.exit(1)

        # delete_unreferenced before uploading if invalidating
        if not delete_unreferenced(options.repo_path):
            sys.exit(1)

        # update after clearing all
        for changes in valid_changes:

            if not run_update_command(options.repo_path,
                                      changes.content['Distribution'],
                                      changes.filename):
                sys.exit(1)
            if options.do_delete:
                print "Removing %s" % changes.folder
                shutil.rmtree(changes.folder)

else:
    print >>sys.stderr, "NO COMMIT OPTION\nWould have run invalidation of dependent packages, invalidation of %s package and uploaded new package" % (options.package)
