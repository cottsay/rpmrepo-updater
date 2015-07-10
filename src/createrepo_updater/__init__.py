import datetime
import createrepo_c as cr
import multiprocessing
import os
import os.path
import Queue
import re
import shutil
import string
import StringIO
import sys

class __ThreadableStringIO(StringIO.StringIO):
    def __init__(self, *args, **kwargs):
        StringIO.StringIO.__init__(self, *args, **kwargs)
        self.queue = multiprocessing.Queue()
        initstr = StringIO.StringIO.getvalue(self)
        if initstr:
            self.queue.put('%s' % (initstr,))
    def write(self, s):
        self.queue.put('%s' % (s,))
    def getvalue(self, *args, **kwargs):
        while True:
            try:
                StringIO.StringIO.write(self, self.queue.get_nowait())
            except Queue.Empty:
                break
        return StringIO.StringIO.getvalue(self, *args, **kwargs)

pkg_list_cache = dict()
pkg_list_cache_orig = dict()

def stamp():
    return '%s' % (datetime.datetime.utcnow(),)

def cr_package_from_file(rpm_file, log=sys.stdout):
    log.write('[%s] Loading information from %s\n' % (stamp(), rpm_file))
    np = cr.package_from_rpm(rpm_file)
    np.location_href = rpm_file
    return np

def cr_get_pkg_list(repo_base, log=sys.stdout):
    if not repo_base in pkg_list_cache:
        log.write('[%s] Parsing repodata from %s\n' % (stamp(), repo_base))
        md = cr.Metadata()
        if not os.path.isfile(os.path.join(repo_base, 'repodata', 'repomd.xml')):
            raise Exception('Invalid repodata path: %s' % (repo_base,))
        md.locate_and_load_xml(repo_base)
        pkgs = set()
        for key in md.keys():
            pkgs.add(md.get(key))
        pkg_list_cache[repo_base] = pkgs
        pkg_list_cache_orig[repo_base] = pkg_list_cache[repo_base].copy()

    return pkg_list_cache[repo_base]

def cr_flush_all_pkg_list(log=sys.stdout):
    log.write('[%s] Flushing all modified package lists to repodata\n' % (stamp(),))

    tlog = __ThreadableStringIO()
    th = []
    for b in pkg_list_cache.keys():
        th += [multiprocessing.Process(target=cr_flush_pkg_list, args=(b, pkg_list_cache[b], False, tlog))]
    for t in th:
        t.start()
    for t in th:
        t.join()
    for b in pkg_list_cache.keys():
        pkg_list_cache_orig[b] = pkg_list_cache[b].copy()
    log.write(tlog.getvalue())

def cr_flush_pkg_list(repo_base, pkglist=None, reset_orig=True, log=sys.stdout):
    if pkglist is None:
        pkglist = cr_get_pkg_list(repo_base, log)

    if pkglist == pkg_list_cache_orig[repo_base]:
        log.write('[%s] Skipping flush for %s (no changes)\n' % (stamp(), repo_base))
        return

    md_tmp = os.path.join(repo_base, '.repodata')
    md_real = os.path.join(repo_base, 'repodata')

    os.mkdir(md_tmp)
    (repomd_data, data_files) = cr_create_md(md_tmp, pkglist, log)
    cr_remove_old_md(md_real, 15, log)
    cr_rename_data_files(md_real, data_files, log)
    cr_write_repomd(md_real, repomd_data, log)
    os.rmdir(md_tmp)

    if reset_orig:
        pkg_list_cache_orig[b] = pkg_list_cache[b]

def cr_remove_downstream(repo_base, tbr, remove_debuginfo=True, pkglist=None, perform_delete=True, log=sys.stdout):
    if pkglist is None:
        pkglist = cr_get_pkg_list(repo_base, log)

    cache = {}

    def __remove_downstream(tbr):
        deadlist = set()
        for p in pkglist:
            if not p.name in cache:
                cache[p.name] = set([pr[0] for pr in p.requires])
            if tbr.intersection(cache[p.name]):
                deadlist.add(p)

        if len(deadlist):
            for p in deadlist:
                pkglist.remove(p)
                if perform_delete:
                    log.write('[%s] Removing dependant %s\n' % (stamp(), p.location_href))
                    try:
                        os.remove(os.path.join(repo_base, p.location_href))
                    except OSError, e:
                        if e.errno != 2:
                            raise
                else:
                    log.write('[%s] DRY-RUN: Removing dependant %s\n' % (stamp(), p.location_href))
                if remove_debuginfo and p.arch.lower() in ['noarch', 'src', 'source', None]:
                    cr_try_remove_debuginfo(repo_base, p.name, perform_delete, log)

            return __remove_downstream(set([d.name for d in deadlist]))

    if not hasattr(tbr, '__iter__'):
        tbr = set([tbr])

    return __remove_downstream(tbr)

def cr_remove_pkg(repo_base, tbr, remove_debuginfo=True, pkglist=None, perform_delete=True, log=sys.stdout):
    if pkglist is None:
        pkglist = cr_get_pkg_list(repo_base, log)

    if not hasattr(tbr, '__iter__'):
        tbr = set([tbr])

    deadlist = set()
    for p in pkglist:
        if p.name in tbr or p.nvra() in tbr:
            deadlist.add(p)

    for p in deadlist:
        pkglist.remove(p)
        if perform_delete:
            log.write('[%s] Specifically removing %s\n' % (stamp(), p.location_href))
            try:
                os.remove(os.path.join(repo_base, p.location_href))
            except OSError, e:
                if e.errno != 2:
                    raise
        else:
            log.write('[%s] DRY-RUN: Specifically removing %s\n' % (stamp(), p.location_href))
        if remove_debuginfo and not p.arch.lower() in ['noarch', 'src', 'source', None]:
            cr_try_remove_debuginfo(repo_base, p.name, perform_delete, log)

def cr_try_remove_debuginfo(repo_base, tbr, perform_delete=True, log=sys.stdout):
    if os.path.basename(os.path.dirname(repo_base + '/')) == 'debug':
        return
    repo_base = os.path.join(repo_base, 'debug')

    if not hasattr(tbr, '__iter__'):
        tbr = set([tbr])

    tbr = [t + '-debuginfo' for t in tbr]

    try:
        pkglist = cr_get_pkg_list(repo_base, log)
    except: # TODO: Make this more specific to "doesn't exist"
        return

    return cr_remove_pkg(repo_base, tbr, False, pkglist, perform_delete, log)

def cr_add_pkg(repo_base, pkgs, pkglist=None, add_debuginfo=True, perform_relocate=True, copy=False, log=sys.stdout):
    if pkglist is None:
        pkglist = cr_get_pkg_list(repo_base, log)

    if not hasattr(pkgs, '__iter__'):
        pkgs = set([pkgs])

    for pkg in pkgs:
        new_path = os.path.join(repo_base, os.path.basename(pkg.location_href))
        if not os.path.isfile(pkg.location_href):
            raise Exception('Target package does not exist or is not a file: %s' % (pkg.location_href,))
        if perform_relocate:
            if copy:
                log.write('[%s] Copying package %s to %s\n' % (stamp(), os.path.basename(pkg.location_href), repo_base))
                shutil.copyfile(pkg.location_href, new_path)
            else:
                try:
                    log.write('[%s] Relocating package %s to %s\n' % (stamp(), os.path.basename(pkg.location_href), repo_base))
                    os.rename(pkg.location_href, new_path)
                except OSError, e:
                    if e.errno != 18:
                        raise
                    log.write('[%s] WARNING: Cross-device link detected for %s. Moving...\n' % (stamp(), os.path.basename(new_path)))
                    shutil.move(pkg.location_href, new_path)
        else:
            log.write('[%s] DRY-RUN: %s package %s to %s\n' % (stamp(), 'Copying' if copy else 'Relocating', os.path.basename(pkg.location_href), repo_base))
        if add_debuginfo:
            cr_try_add_debuginfo(repo_base, set([pkg]), perform_relocate, copy, log)
        pkg.location_href = os.path.basename(new_path)
    log.write('[%s] Adding %d packages to metadata\n' % (stamp(), len(pkgs)))
    pkglist.update(pkgs)

def cr_try_add_debuginfo(repo_base, pkgs, perform_relocate=True, copy=False, log=sys.stdout):
    if os.path.basename(os.path.dirname(repo_base + '/')) == 'debug':
        return
    repo_base = os.path.join(repo_base, 'debug')

    if not hasattr(pkgs, '__iter__'):
        pkgs = set([pkgs])

    dbgpkgs = dict()

    for pkg in pkgs:
        dbg_repo_base = os.path.join(os.path.dirname(pkg.location_href), 'debug')
        try:
            dbg_pkglist = cr_get_pkg_list(dbg_repo_base, log)
        except: # TODO: Make this more specific to "doesn't exist"
            continue

        this_dbginfo_name = pkg.name + '-debuginfo'

        found_dbgpkgs = [p.copy() for p in dbg_pkglist if p.name == this_dbginfo_name]

        if not found_dbgpkgs:
            continue

        for dp in found_dbgpkgs:
            dp.location_href = os.path.join(dbg_repo_base, dp.location_href)

        if not dbg_repo_base in dbgpkgs:
            dbgpkgs[dbg_repo_base] = set()

        dbgpkgs[dbg_repo_base].update(found_dbgpkgs)

    for dbgpkg in dbgpkgs.values():
        cr_add_pkg(repo_base, dbgpkg, None, False, perform_relocate, copy, log)

def cr_create_md(repodata_path, pkglist=None, log=sys.stdout):
    if pkglist is None:
        pkglist = cr_get_pkg_list(repo_base, log)

    pri_xml_path = os.path.join(repodata_path, 'primary.xml.gz')
    fil_xml_path = os.path.join(repodata_path, 'filelists.xml.gz')
    oth_xml_path = os.path.join(repodata_path, 'other.xml.gz')
    pri_db_path = os.path.join(repodata_path, 'primary.sqlite')
    fil_db_path = os.path.join(repodata_path, 'filelists.sqlite')
    oth_db_path = os.path.join(repodata_path, 'other.sqlite')

    def __create_xml(queues, xml_path, xml_func, name):
        cs = cr.ContentStat(cr.SHA256)
        xml = xml_func(xml_path, contentstat=cs)

        xml.set_num_of_pkgs(len(pkglist))

        for pkg in pkglist:
            xml.add_pkg(pkg)

        xml.close()

        queues['master'].put(((name, xml_path), (cs.checksum, cs.size, cs.checksum_type)), True)

    def __create_db(queues, db_path, db_func, name):
        db = db_func(db_path)

        for pkg in pkglist:
            db.add_pkg(pkg)

        db.dbinfo_update(queues[name].get(True))

        db.close()

        cs = cr.ContentStat(cr.SHA256)
        cr.compress_file_with_stat(db_path, db_path + cr.compression_suffix(cr.BZ2_COMPRESSION), cr.BZ2_COMPRESSION, cs)
        os.remove(db_path)
        queues['master'].put(((name + '_db', db_path + cr.compression_suffix(cr.BZ2_COMPRESSION)), (cs.checksum, cs.size, cs.checksum_type)), True)

    queue_manager = multiprocessing.Manager()
    queues = dict({
        'master':queue_manager.Queue(),
        'primary':queue_manager.Queue(),
        'filelists':queue_manager.Queue(),
        'other':queue_manager.Queue(),
	})

    log.write('[%s] Generating metadata in %s\n' % (stamp(), repodata_path))

    th = [0] * 6
    th[0] = multiprocessing.Process(target=__create_xml, args=(queues, pri_xml_path, cr.PrimaryXmlFile, 'primary'))
    th[0].start()
    th[1] = multiprocessing.Process(target=__create_xml, args=(queues, fil_xml_path, cr.FilelistsXmlFile, 'filelists'))
    th[1].start()
    th[2] = multiprocessing.Process(target=__create_xml, args=(queues, oth_xml_path, cr.OtherXmlFile, 'other'))
    th[2].start()
    th[3] = multiprocessing.Process(target=__create_db, args=(queues, pri_db_path, cr.PrimarySqlite, 'primary'))
    th[3].start()
    th[4] = multiprocessing.Process(target=__create_db, args=(queues, fil_db_path, cr.FilelistsSqlite, 'filelists'))
    th[4].start()
    th[5] = multiprocessing.Process(target=__create_db, args=(queues, oth_db_path, cr.OtherSqlite, 'other'))
    th[5].start()

    repomd = cr.Repomd()

    data_files = set()
    for i in range(0, 6):
        rf = queues['master'].get(True)
        r = cr.RepomdRecord(*rf[0])
        r.checksum_open_type = cr.checksum_name_str(rf[1][2])
        r.checksum_open = rf[1][0]
        r.size_open = rf[1][1]
        r.fill(cr.SHA256)
        if not rf[0][0].endswith('_db'):
            queues[rf[0][0]].put(r.checksum, True)
        r.rename_file()
        r.location_href = os.path.join('repodata', os.path.basename(r.location_href))
        data_files.add(r.location_real)
        repomd.set_record(r)

    for t in th:
        t.join()

    repomd.sort_records()
    return (repomd.xml_dump(), data_files)

def cr_remove_old_md(repodata_path, num_to_keep, log=sys.stdout):
    types = ['primary.xml', 'primary.sqlite', 'filelists.xml',
		'filelists.sqlite', 'other.xml', 'other.sqlite']

    present = {}
    for t in types:
        present[t] = []

    for top, dirs, files in os.walk(repodata_path):
        for f in files:
            for t in types:
                if t in f:
                    present[t] += [(os.stat(os.path.join(repodata_path, f))[8], f)]

    cnt = 0
    for t in types:
        present[t] = sorted(present[t], key=lambda k: k[0])
        for f in present[t][:-num_to_keep]:
            os.remove(os.path.join(repodata_path, f[1]))
            cnt += 1

    log.write('[%s] Removed %d old metadata files\n' % (stamp(), cnt))

def cr_rename_data_files(newdir, data_files, log=sys.stdout):
    log.write('[%s] Moving metadata to %s\n' % (stamp(), newdir))
    for f in data_files:
        os.rename(f, os.path.join(newdir, os.path.basename(f)))

def cr_write_repomd(repodata_path, new_contents, log=sys.stdout):
    log.write('[%s] Writing repomd.xml for %s\n' % (stamp(), repodata_path))
    open(os.path.join(repodata_path, 'repomd.xml'), 'w').write(new_contents)

fver = re.compile('(.*)\.fc(\d+)')

def cr_determine_subrepo(pkg, log=sys.stdout):
    repoarch = pkg.arch

    fcver = re.match(fver, pkg.release).group(2)

    if repoarch == 'noarch':
        # We can't extract the target arch from the RPM. We have two choices:
        # - Try to extract the target arch from the upload directory
        # - Copy the noarch rpm to each available arch
        #
        # We'll do the former if extraction seems possible. The latter sounds
        # sort-of unsafe, so bail otherwise

        # As a path check, verfiy that our fedora version matches
        fcver_dir = os.path.basename(os.path.dirname(os.path.dirname(pkg.location_href)))
        if fcver_dir == fcver:
            repoarch = os.path.basename(os.path.dirname(pkg.location_href))
        else:
            raise ValueError('No valid repository for ' + str(pkg.location_href))

    if repoarch in ['i486', 'i586', 'i686']:
        repoarch = 'i386'
    elif repoarch in ['armv5tel']:
        repoarch = 'arm'
    elif repoarch in ['armv7hl', 'armv7hnl']:
        repoarch = 'armhfp'
    elif repoarch in ['src', 'source']:
        repoarch = 'SRPMS'

    if pkg.name.endswith('-debuginfo'):
        return os.path.join(fcver, repoarch, 'debug')
    else:
        return os.path.join(fcver, repoarch)

