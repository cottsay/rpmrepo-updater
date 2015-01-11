#!/bin/env python
import argparse
import createrepo_updater
import os
import re
import sys

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

    if args.clean:
        nfo('Performing \'clean\'...')

        staged_for_removal = dict()

        dest_repo = load_repo(args.dest_repo, args.release, args.arch)

        for (rel, arches) in dest_repo.iteritems():
            for (arch, repo) in arches.iteritems():
                local_removal = set()
                for pkg in repo:
                    if filter.match(pkg.name):
                        local_removal.add(pkg.name)

                if local_removal:
                    if not rel in staged_for_removal:
                        staged_for_removal[rel] = dict()
                    staged_for_removal[rel][arch] = local_removal
                    dbg('Staged {0} packages for removal from {1}'.format(len(local_removal), os.path.join(rel, arch)))

        if staged_for_removal:
            for rel in staged_for_removal.keys():
                for arch in staged_for_removal[rel].keys():
                    tgtpath = os.path.join(args.dest_repo, rel, arch)
                    nfo('{0}Removing {1} packages from {2}'.format('' if args.commit else 'DRY-RUN: ', len(staged_for_removal[rel][arch]), tgtpath))
                    createrepo_updater.cr_remove_pkg(tgtpath, staged_for_removal[rel][arch], remove_debuginfo=True, pkglist=None, perform_delete=args.commit, log=dbghandle)
        else:
            nfo('No packages marked for removal.')

    if args.update:
        nfo('Performing \'update\'...')

        staged_for_update = dict()

        source_repo = load_repo(args.source_repo, args.release, args.arch)

        for (rel, arches) in source_repo.iteritems():
            for (arch, repo) in arches.iteritems():
                local_update = set()
                for pkg in repo:
                    if filter.match(pkg.name):
                        newpkg = pkg.copy()
                        newpkg.location_href = os.path.join(args.source_repo, rel, arch, newpkg.location_href)
                        local_update.add(newpkg)

                if local_update:
                    if not rel in staged_for_update:
                        staged_for_update[rel] = dict()
                    staged_for_update[rel][arch] = local_update
                    dbg('Staged {0} packages for update from {1}'.format(len(local_update), os.path.join(rel, arch)))

        if staged_for_update:
            for rel in staged_for_update.keys():
                for arch in staged_for_update[rel].keys():
                    tgtpath = os.path.join(args.dest_repo, rel, arch)
                    nfo('{0}Copying {1} packages to {2}'.format('' if args.commit else 'DRY-RUN: ', len(staged_for_update[rel][arch]), tgtpath))
                    # This system doesn't allow for duplicate package names. This is still, however, not the same as cleaning.
                    createrepo_updater.cr_remove_pkg(tgtpath, [p.name for p in staged_for_update[rel][arch]], remove_debuginfo=True, pkglist=None, perform_delete=args.commit, log=dbghandle)
                    createrepo_updater.cr_add_pkg(tgtpath, staged_for_update[rel][arch], add_debuginfo=True, pkglist=None, perform_relocate=args.commit, copy=True, log=dbghandle)
        else:
            nfo('No packages marked for update.')

    if args.commit:
        nfo('Flusing repodata...')
        createrepo_updater.cr_flush_all_pkg_list(log=dbghandle)

    nfo('Repository operations complete.')

if __name__ == '__main__':
    main(parse_args())
