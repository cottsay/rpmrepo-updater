#!/bin/env python
import argparse
import createrepo_updater
import os
import re
import sys

from distutils.version import LooseVersion

parser = argparse.ArgumentParser()

def is_dir_readable(path):
    if not os.path.isdir(path):
        raise argparse.ArgumentTypeError('Must be a directory')
    elif not os.access(path, os.R_OK):
        raise argparse.ArgumentTypeError('Directory must be readable')
    return path

def is_dir_writeable(path):
    if not os.path.isdir(path):
        raise argparse.ArgumentTypeError('Must be a directory')
    elif not os.access(path, os.W_OK):
        raise argparse.ArgumentTypeError('Directory must be writeable')
    return path

# Options
parser.add_argument('--arches', dest='arch', nargs='+', help='Architecture(s) to sync', choices=['SRPMS', 'armhfp', 'i386', 'x86_64'])
parser.add_argument('--commit', dest='commit', action='store_true', default=False, help='Actually perform sync')
parser.add_argument('--hardlink', dest='hardlink', action='store_true', default=False, help='Perform a hard link instead of copy')
parser.add_argument('--release', dest='release', nargs='+', type=int, help='Fedora release(s) to sync')
parser.add_argument('--debug', dest='debug', action='store_true', default=False, help='Verbose output')
parser.add_argument('--fast', dest='fast', action='store_true', default=False, help='Look for shortcuts to speed-up the sync')
parser.add_argument('--verify-exist', dest='verify_exist', action='store_true', default=False, help='Verify existence packages in destination repo and remove when absent')
parser.add_argument('--sign', dest='sign', action='store_true', default=False, help='Sign packages as they are added to the repository')
parser.add_argument('--filter', dest='filter', default='', help='Package filter (regex allowed)')

# Commands
parser.add_argument('--clean', dest='clean', action='store_true', default=False, help='Remove packages matching the filter from the repo')
parser.add_argument('--update', dest='update', action='store_true', default=False, help='Add packages from upstream into downstream')

# Arguments
parser.add_argument('source_repo', type=is_dir_readable, help='Upstream repository to sync from (never modified)')
parser.add_argument('dest_repo', type=is_dir_writeable, help='Downstream repository to operate on')

dbghandle = sys.stdout

def nfo(msg):
    sys.stdout.write('[{0}] {1}\n'.format(createrepo_updater.stamp(), msg.replace('\n', '\n{0}'.format(' ' * 29))))

def dbg(msg):
    dbghandle.write('[{0}] DEBUG: {1}\n'.format(createrepo_updater.stamp(), msg))

def wrn(msg):
    sys.stderr.write('[{0}] WARNING: {1}\n'.format(createrepo_updater.stamp(), msg))

def parse_args():
    args = parser.parse_args()

    if os.path.normpath(args.source_repo) == os.path.normpath(args.dest_repo):
        parser.error('source_repo and dest_repo must be different')

    if args.sign:
        if args.hardlink:
            wrn('hardlinking is not possible when signing packages. Disabling hardlinking...')
            args.hardlink = False
        elif not args.update:
            wrn('hardlinking is only possible with the --update command. Disabling hardlinking...')
            args.hardlink = False

    if args.fast:
        if not args.clean or not args.update:
            wrn('fast option is only possible with both --clean and --update. Disabling fast...')
            args.fast = False

    if not args.debug:
        global dbg
        global dbghandle
        dbg = lambda msg: None
        dbghandle = open(os.devnull, 'w')

    if args.release:
        dbg('Limiting releases to: %s' % (args.release,))

    if args.arch:
        dbg('Limiting arches to: %s' % (args.arch,))

    dbg('Finished parsing args')

    return args

def load_repo(path, releases=[], arches=[]):
    ret = dict()

    if not releases:
        releases = os.listdir(path)
        for release in set(releases):
            relpath = os.path.join(path, release)
            if not os.path.isdir(relpath) or not os.access(relpath, os.R_OK):
               dbg('Ignoring non-directory or non-readable {0}'.format(relpath)) 
               releases.remove(release)
    else:
        (releases, oldrel) = ([], releases)
        for release in oldrel:
            releases += ['{0}'.format(release)]

    for release in releases:
        ret[release] = dict()
        relarches = arches
        relpath = os.path.join(path, release)

        if not relarches:
            relarches = os.listdir(relpath)
            for arch in set(relarches):
                archpath = os.path.join(relpath, arch)
                if not os.path.isdir(archpath) or not os.access(archpath, os.R_OK):
                   dbg('Ignoring non-directory or non-readable {0}'.format(archpath)) 
                   relarches.remove(arch)

        for arch in relarches:
            archpath = os.path.join(relpath, arch)
            ret[release][arch] = createrepo_updater.cr_get_pkg_list(archpath, log=dbghandle)

    return ret

def main(args):
    nfo('Starting repository operations...')

    filter = re.compile(args.filter)
    dbg('Source Repository: {0}'.format(args.source_repo))
    dbg('Destination Repository: {0}'.format(args.dest_repo))

    staged_for_removal = dict()
    staged_for_update = dict()
    staged_for_removal_verify = dict()

    if args.clean:
        nfo('Performing \'clean\'...')

        dest_repo = load_repo(args.dest_repo, args.release, args.arch)

        for (rel, arches) in dest_repo.iteritems():
            for (arch, repo) in arches.iteritems():
                local_removal = dict()
                for pkg in repo:
                    if filter.match(pkg.name):
                        if pkg.name in local_removal:
                            newver = pkg.version + pkg.release
                            othver = local_removal[pkg.name].version + local_removal[pkg.name].release
                            wrn('Found multiple versions of \'{0}\' in downstream repo ({1} and {2})'.format(pkg.name, othver, newver))
                            if LooseVersion(newver) < LooseVersion(othver):
                                continue
                        local_removal[pkg.name] = pkg

                if local_removal:
                    if not rel in staged_for_removal:
                        staged_for_removal[rel] = dict()
                    staged_for_removal[rel][arch] = local_removal
                    dbg('Staged {0} packages for removal from {1}'.format(len(local_removal), os.path.join(rel, arch)))

    if args.update:
        nfo('Performing \'update\'...')

        source_repo = load_repo(args.source_repo, args.release, args.arch)

        for (rel, arches) in source_repo.iteritems():
            for (arch, repo) in arches.iteritems():
                local_update = dict()
                for pkg in repo:
                    if filter.match(pkg.name):
                        newpkg = pkg.copy()
                        newpkg.location_href = os.path.join(args.source_repo, rel, arch, newpkg.location_href)
                        if newpkg.name in local_update:
                            newver = newpkg.version + '-' + newpkg.release
                            othver = local_update[newpkg.name].version + '-' + local_update[newpkg.name].release
                            wrn('Found multiple versions of \'{0}\' in upstream repo ({1} and {2})'.format(newpkg.name, othver, newver))
                            if LooseVersion(newver) < LooseVersion(othver):
                                continue
                        local_update[newpkg.name] = newpkg

                if local_update:
                    if not rel in staged_for_update:
                        staged_for_update[rel] = dict()
                    staged_for_update[rel][arch] = local_update
                    dbg('Staged {0} packages for update from {1}'.format(len(local_update), os.path.join(rel, arch)))

    if args.fast:
        nfo('Performing magic speedups...')

        speedups = 0

        for rel in staged_for_removal.keys():
            if rel in staged_for_update:
                for arch in staged_for_removal[rel].keys():
                    if arch in staged_for_update[rel]:
                        for pkg in staged_for_removal[rel][arch].keys():
                            if pkg in staged_for_update[rel][arch]:
                                if staged_for_removal[rel][arch][pkg].pkgId == staged_for_update[rel][arch][pkg].pkgId:
                                    dbg('Package \'{0}\' is same in source and destination. Skipping...'.format(pkg))
                                    speedups += 1
                                    del staged_for_removal[rel][arch][pkg]
                                    del staged_for_update[rel][arch][pkg]
        nfo('Saved {0} deletions and copies'.format(speedups))

    if staged_for_removal:
        for rel in staged_for_removal.keys():
            for arch in staged_for_removal[rel].keys():
                tgtpath = os.path.join(args.dest_repo, rel, arch)
                nfo('{0}Removing {1} packages from {2}'.format('' if args.commit else 'DRY-RUN: ', len(staged_for_removal[rel][arch]), tgtpath))
                createrepo_updater.cr_remove_pkg(tgtpath, set(staged_for_removal[rel][arch].keys()), remove_debuginfo=True, pkglist=None, perform_delete=args.commit, log=dbghandle)
    elif args.clean:
        nfo('No packages marked for removal.')

    if staged_for_update:
        for rel in staged_for_update.keys():
            for arch in staged_for_update[rel].keys():
                tgtpath = os.path.join(args.dest_repo, rel, arch)
                nfo('{0}Copying {1} packages to {2}'.format('' if args.commit else 'DRY-RUN: ', len(staged_for_update[rel][arch]), tgtpath))
                 # This system doesn't allow for duplicate package names. This is still, however, not the same as cleaning.
                createrepo_updater.cr_remove_pkg(tgtpath, set(staged_for_update[rel][arch].keys()), remove_debuginfo=True, pkglist=None, perform_delete=args.commit, log=dbghandle)
                createrepo_updater.cr_add_pkg(tgtpath, set(staged_for_update[rel][arch].values()), add_debuginfo=True, pkglist=None, perform_relocate=args.commit, copy=True, log=dbghandle)
    elif args.update:
        nfo('No packages marked for update.')

    if args.verify_exist:
        nfo('Verifying packages in destination repo...')

        dest_repo = load_repo(args.dest_repo, args.release, args.arch)

        for (rel, arches) in dest_repo.iteritems():
            for (arch, repo) in arches.iteritems():
                local_removal = dict()
                local_match = dict()
                tgtpath = os.path.join(args.dest_repo, rel, arch)
                for pkg in repo:
                    if filter.match(pkg.name):
                        pkgpath = os.path.join(tgtpath, pkg.location_href)
                        if not os.path.isfile(pkgpath):
                            local_removal[pkg.name] = pkg
                        else:
                            if pkg.name in local_match:
                                newver = pkg.version + '-' + pkg.release
                                othver = local_match[pkg.name].version + '-' + local_match[pkg.name].release
                                wrn('Found multiple versions of \'{0}\' in downstream repo ({1} and {2})'.format(pkg.name, othver, newver))
                                if LooseVersion(newver) < LooseVersion(othver):
                                    wrn('Staging the older ({0}) for removal'.format(pkg.nvra()))
                                    local_removal[pkg.nvra()] = pkg
                                    continue
                                else:
                                    wrn('Staging the older ({0}) for removal'.format(local_match[pkg.name].nvra()))
                                    local_removal[local_match[pkg.name].nvra()] = local_match[pkg.name]
                            local_match[pkg.name] = pkg

                if local_removal:
                    if not rel in staged_for_removal_verify:
                        staged_for_removal_verify[rel] = dict()
                    staged_for_removal_verify[rel][arch] = local_removal
                    dbg('Staged {0} non-existent or outdated packages for removal from {1}'.format(len(local_removal), os.path.join(rel, arch)))

    if staged_for_removal_verify:
        for rel in staged_for_removal_verify.keys():
            for arch in staged_for_removal_verify[rel].keys():
                tgtpath = os.path.join(args.dest_repo, rel, arch)
                nfo('{0}Removing {1} non-existent or outdated packages from {2}'.format('' if args.commit else 'DRY-RUN: ', len(staged_for_removal_verify[rel][arch]), tgtpath))
                createrepo_updater.cr_remove_pkg(tgtpath, set(staged_for_removal_verify[rel][arch].keys()), remove_debuginfo=True, pkglist=None, perform_delete=args.commit, log=dbghandle)
    elif args.verify_exist:
        nfo('All packages in destination repo exist on disk.')

    if args.commit:
        nfo('Flusing repodata...')
        createrepo_updater.cr_flush_all_pkg_list(log=dbghandle)

    nfo('Repository operations complete.')

if __name__ == '__main__':
    main(parse_args())
