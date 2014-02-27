import subprocess
import fcntl
import time
import sys
import shutil
import createrepo
import yum.misc
import os
import rpminfo

# TODO: Cache this
def make_cr_conf():
    def_workers = os.nice(0)
    if def_workers > 0:
        def_workers = 1
    else:
        def_workers = 0

    conf = createrepo.MetaDataConfig()
    conf.excludes = ['debug/*']
    conf.quiet = True
    conf.checksum = yum.misc._default_checksums[0]
    conf.database = True
    conf.update = True
    conf.retain_old_md = 10
    conf.compress_type = 'compat'
    conf.workers = def_workers
    conf.split = True
    return conf

class LockContext:
    def __init__(self, lockfilename = None, timeout = 3000):
        if lockfilename:
            self.lockfilename = lockfilename
        else:
            self.lockfilename = '/tmp/prepare_sync.py.lock'

        self.timeout = timeout

    def __enter__(self):
        self.lfh = open(self.lockfilename, 'w')

        file_locked = False
        for i in xrange(self.timeout):

            try:

                fcntl.lockf(self.lfh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                file_locked = True
                break
            except IOError, ex:
                print "could not get lock on %s. Waiting one second (%d of %d)" % (self.lockfilename, i, self.timeout)
                time.sleep(1)
        if not file_locked:
            raise IOError("Could not lock file %s with %d retries"% (self.lockfilename, self.timeout) )

        return self

    def __exit__(self, exception_type, exception_val, trace):
        self.lfh.close()
        return False

def find_target_subrepos(repo_path, package):
    if not package.fcdistro:
        raise ValueError('Non-Fedora release tag ' + str(package.release) + ' on package ' + str(package.path))
    fcver = str(package.fcdistro)
    if package.is_src or package.arch == 'src':
        candidate = os.path.join(repo_path, 'linux', fcver, 'SRPMS')
        if not os.path.exists(os.path.join(candidate, 'repodata', 'repomd.xml')):
            raise ValueError('No valid repository for ' + str(package.path))
        return set((candidate,))
    elif package.arch == 'noarch':
        arches = set()
        for candidate in [x[0] for x in os.walk(os.path.join(repo_path, 'linux', fcver))]:
            candidate = os.path.join(repo_path, 'linux', fcver, candidate)
            if candidate != 'SRPMS' and os.file.exists(os.path.join(candidate, 'repodata', 'repomd.xml')):
                arches.add(candidate)
        if not arches:
            raise ValueError('No valid repository for ' + str(package.path))
        return arches
    else:
        if package.arch in ['i486', 'i586', 'i686']:
            repoarch = 'i386'
        else:
            repoarch = package.arch
        if package.name.endswith('-debuginfo'):
            candidate = os.path.join(repo_path, 'linux', fcver, str(repoarch), 'debug')
        else:
            candidate = os.path.join(repo_path, 'linux', fcver, str(repoarch))
        if not os.path.exists(os.path.join(candidate, 'repodata', 'repomd.xml')):
            raise ValueError('No valid repository for ' + str(package.path))
        return set((candidate,))

def update_metadata(repo_path):
    if hasattr(repo_path, '__iter__'):
        for repo in repo_path:
            update_metadata(repo)
        return

    conf = make_cr_conf()
    conf.directory = repo_path
    conf.directories = [repo_path]

    print "Updating repository at " + repo_path
    mdgen = createrepo.SplitMetaDataGenerator(config_obj=conf)
    mdgen.doPkgMetadata()
    mdgen.doRepoMetadata()
    mdgen.doFinalMove()

def place_package(repo_path, package, delayed_metadata = None):
    md = set()
    if hasattr(package, '__iter__'):
        for pkg in package:
            place_package(repo_path, pkg, delayed_metadata = md)
    else:
        for subrepo in find_target_subrepos(repo_path, package):
            print "Placing " + package.path + " at " + subrepo
            shutil.copy(package.path, subrepo)
            md.add(subrepo)
    if delayed_metadata is not None:
        delayed_metadata |= md
    else:
        update_metadata(md)

def remove_package(repo_path, package, cache = None, delayed_metadata = None):
    if cache is None:
        cache = {}
    md = set()
    if hasattr(package, '__iter__'):
        for pkg in package:
            remove_package(repo_path, pkg, cache = cache, delayed_metadata = md)
    else:
        for subrepo in find_target_subrepos(repo_path, package):
            if subrepo not in cache:
                cache[subrepo] = rpminfo.read_repository(subrepo)
            to_be_removed = set()
            for pkg in cache[subrepo]:
                if pkg.name == package.name:
                    to_be_removed.add(pkg)

            for pkg in to_be_removed:
                if pkg not in cache[subrepo]:
                    continue
                pkgpath = os.path.join(subrepo, pkg.path)
                if os.path.exists(pkgpath):
                    print "Explicitly Removing " + str(pkgpath)
                    os.remove(pkgpath)
                md.add(subrepo)
                cache[subrepo].remove(pkg)
                remove_debuginfo(subrepo, pkg.name, cache, md)

    if delayed_metadata is not None:
        delayed_metadata |= md
    else:
        update_metadata(md)

# TODO: Thread this?
def remove_dependent(repo_path, package, cache = None, delayed_metadata = None):
    if cache is None:
        cache = {}
    md = set()
    if hasattr(package, '__iter__'):
        for pkg in package:
            remove_package(repo_path, pkg, cache = cache, delayed_metadata = md)
    else:
        to_be_removed = set()
        for subrepo in find_target_subrepos(repo_path, package):
            if subrepo not in cache:
                cache[subrepo] = rpminfo.read_repository(subrepo)
            for pkg in cache[subrepo]:
                if package.provides.intersects(pkg.requires):
                    to_be_removed.add(pkg)

        for pkg in to_be_removed:
            if pkg not in cache[subrepo]:
                continue # Removed by recursive call
            pkgpath = os.path.join(subrepo, pkg.path)
            if os.path.exists(pkgpath):
                print "Removing Dependant " + str(pkgpath)
                os.remove(pkgpath)
            md.add(subrepo)
            cache[subrepo].remove(pkg)
            remove_debuginfo(subrepo, pkg.name, cache, md)
            remote_dependent(repo_path, pkg, cache, md)

    if delayed_metadata is not None:
        delayed_metadata |= md
    else:
        update_metadata(md)

def remove_debuginfo(subrepo, packagename, cache = None, delayed_metadata = None):
    if cache is None:
        cache = {}
    md = set()
    if hasattr(packagename, '__iter__'):
        for pkg in packagename:
            remove_debuginfo(subrepo, pkg, cache = cache, delayed_metadata = md)
    else:
        debugrepo = os.path.join(subrepo, 'debug')
        if not os.path.exists(os.path.join(debugrepo, 'repodata', 'repomd.xml')):
            return
        if debugrepo not in cache:
            cache[debugrepo] = rpminfo.read_repository(debugrepo)
        packagename += '-debuginfo'
        to_be_removed = set()
        for pkg in cache[debugrepo]:
            if pkg.name == packagename:
                to_be_removed.add(pkg)

        for pkg in to_be_removed:
            if pkg not in cache[debugrepo]:
                continue
            pkgpath = os.path.join(debugrepo, pkg.path)
            if os.path.exists(pkgpath):
                print "Removing debuginfo " + str(pkgpath)
                os.remove(pkgpath)
            md.add(debugrepo)
            cache[debugrepo].remove(pkg)
            
    if delayed_metadata is not None:
        delayed_metadata |= md
    else:
        update_metadata(md)

