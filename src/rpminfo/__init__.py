from bz2 import decompress as bz2_decompress
from gzip import GzipFile
from xml.dom import minidom
import os
import re
import rpm
from urllib2 import urlopen
from urlparse import urlparse
import sqlite3
from StringIO import StringIO
import struct
import sys
from tempfile import mktemp
from threading import Thread

ts = rpm.TransactionSet()
# We really don't care about signatures...
ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES)
fver = re.compile('(.*)\.fc(\d+)')

class RpmInfo:
    name = None
    version = None
    release = None
    is_src = None
    arch = None
    requires = None
    provides = None
    path = None
    __fcdistro = None
    __pkgrel = None

    def __init__(self, name = None, version = None, release = None,
                 is_src = None, arch = None, requires = None, provides = None,
                 path = None):
        self.name = name
        self.version = version
        self.release = release
        self.is_src = is_src
        self.arch = arch
        self.requires = requires
        self.provides = provides
        self.path = path

    @property
    def fcdistro(self):
        if not self.__fcdistro:
            try:
                self.__pkgrel = int(re.match(fver, self.release).group(1))
                self.__fcdistro = int(re.match(fver, self.release).group(2))
            except:
                pass

        return self.__fcdistro

    @property
    def pkgrel(self):
        if not self.__pkgrel:
            try:
                self.__pkgrel = int(re.match(fver, self.release).group(1))
                self.__fcdistro = int(re.match(fver, self.release).group(2))
            except:
                pass

        return self.__pkgrel

    def has_requires(self, reqs):
        if not hasattr(reqs, '__iter__'):
            return bool(reqs in self.requires)

        return bool(any(i in self.requires for i in reqs))

    def has_provides(self, provs):
        if not hasattr(provs, '__iter__'):
            return bool(provs in self.provides)

        return bool(any(i in self.provides for i in provs))


def read_from_rpm(init):

    if type(init) == str:
        th = None
        url = urlparse(init)
        if url.scheme not in [None, '', 'file']:
            fdno, fdno_w = os.pipe()
            try:
                fdurl = urlopen(init)
                try:
                    if fdurl.info()['Content-length'] < 0x70:
                        raise rpm.error("error reading package header")
                except KeyError:
                    pass

                # Read the magic
                buff = fdurl.read(0x04)

                if buff[0:4] != '\xed\xab\xee\xdb':
                    raise rpm.error("error reading package header")

                # Read the lead and the signature structure
                buff += fdurl.read(0x6c)

                # Read the signature and the header structure
                tbr = 0x10 * struct.unpack(">i", buff[-8:-4])[0] + struct.unpack(">i", buff[-4:])[0]
                tbr += 0x10 + ( 0x8 - (tbr % 0x8 ) ) % 0x8
                buff += fdurl.read(tbr)

                # Read the rest of the header
                tbr = 0x10 * struct.unpack(">i", buff[-8:-4])[0] + struct.unpack(">i", buff[-4:])[0]
                tbr += ( 0x8 - ( tbr % 0x8 ) ) % 0x8 + 100
                buff += fdurl.read(tbr)
                fdurl.close()

                # If the pipe buffer fills, we'll block, so the pipe write needs to be threaded
                th = Thread(target=os.write, args=(fdno_w, buff))
                th.start()
            except:
                os.close(fdno)
                raise
            finally:
                os.close(fdno_w)
        else:
            fdno = os.open(url.netloc + url.path, os.O_RDONLY)
        try:
            hdr = ts.hdrFromFdno(fdno)
        finally:
            os.close(fdno)
            if th:
                th.join(1.0)
    elif type(init) == int:
        hdr = ts.hdrFromFdno(init)
    elif type(init) == rpm.hdr:
        hdr = init
    else:
        raise TypeError('Could not initialize from type ' + str(type(init)))

    return RpmInfo(name = hdr[rpm.RPMTAG_NAME],
                   version = hdr[rpm.RPMTAG_VERSION],
                   release = hdr[rpm.RPMTAG_RELEASE],
                   is_src = not bool( hdr[rpm.RPMTAG_SOURCERPM] ),
                   arch = hdr[rpm.RPMTAG_ARCH],
                   requires = set(hdr[rpm.RPMTAG_REQUIRES]),
                   provides = set(hdr[rpm.RPMTAG_PROVIDES]),
                   path = init)


def read_repository(repo_path):
    try:
        return read_repository_sqlite(repo_path)
    except IOError:
        return read_repository_xml(repo_path)


def read_repository_xml(repo_path):
    primary_xml = find_metadata_file(repo_path, 'primary')
    return read_primary_xml(repo_path, primary_xml)


def read_repository_sqlite(repo_path):
    primary_sqlite = find_metadata_file(repo_path, 'primary_db')
    return read_primary_sqlite(repo_path, primary_sqlite)


def find_metadata_file(repo_path, metadata = 'primary_db', repomd_xml = os.path.join('repodata', 'repomd.xml')):
    repomd_xml = os.path.join(repo_path, repomd_xml)
    url = urlparse(repomd_xml)
    if url.scheme not in [None, '', 'file']:
        fdurl = urlopen(repomd_xml)
        repomd_data = minidom.parseString(fdurl.read()).getElementsByTagName('data')
        fdurl.close()
    else:
        repomd_data = minidom.parse(url.netloc + url.path).getElementsByTagName('data')
    for data_entry in repomd_data:
        if data_entry.getAttribute('type') == metadata:
            return data_entry.getElementsByTagName('location')[0].getAttribute('href')

    raise IOError('Could not find metadata file \'' + metadata + '\'')


def read_primary_xml(repo_path, primary_xml = os.path.join('repodata', 'primary.xml')):
    primary_xml = os.path.join(repo_path, primary_xml)
    url = urlparse(primary_xml)
    if url.scheme not in [None, '', 'file']:
        fdurl = urlopen(primary_xml)
        primary_xml_str = fdurl.read()
        fdurl.close()

        if primary_xml.endswith('.gz'):
            primary_xml_stream = StringIO(primary_xml_str)
            primary_xml_gz = GzipFile(fileobj=primary_xml_stream, mode='rb')
            primary_xml_str = primary_xml_gz.read()

        pkgdb = minidom.parseString(primary_xml_str)
    else:
        if primary_xml.endswith('.gz'):
            primary_xml_gz = GzipFile(primary_xml, mode='rb')
            primary_xml_str = primary_xml_gz.read()
            pkgdb = minidom.parseString(primary_xml_str)
        elif primary_xml.endswith('.xml'):
            pkgdb = minidom.parse(primary_xml)

    # Parse packages
    pkgs = set()
    for pkg in pkgdb.getElementsByTagName('package'):
        if pkg.getAttribute('type') != 'rpm':
            continue
        rpm_name = pkg.getElementsByTagName('name')[0].firstChild.data
        rpm_version_obj = pkg.getElementsByTagName('version')[0]
        rpm_version = rpm_version_obj.getAttribute('ver')
        rpm_release = rpm_version_obj.getAttribute('rel')
        rpm_arch = pkg.getElementsByTagName('arch')[0].firstChild.data
        try:
            rpm_format_obj = pkg.getElementsByTagName('format')[0]
        except (AttributeError, IndexError):
            rpm_requires = rpm_provides = set()
        else:
            try:
                rpm_requires_obj = rpm_format_obj.getElementsByTagName('rpm:requires')[0]
                rpm_requires = set(r.getAttribute('name') for r in rpm_requires_obj.getElementsByTagName('rpm:entry'))
            except (AttributeError, IndexError):
                rpm_requires = set()
            try:
                rpm_provides_obj = rpm_format_obj.getElementsByTagName('rpm:provides')[0]
                rpm_provides = set(p.getAttribute('name') for p in rpm_provides_obj.getElementsByTagName('rpm:entry'))
            except (AttributeError, IndexError):
                rpm_provides = set()
        rpm_location_obj = pkg.getElementsByTagName('location')[0]
        rpm_path = os.path.join(repo_path, rpm_location_obj.getAttribute('href'))
        pkgs.add(RpmInfo(name = rpm_name,
                         version = rpm_version,
                         release = rpm_release,
                         arch = rpm_arch,
                         is_src = bool(rpm_arch == 'src'),
                         requires = rpm_requires,
                         provides = rpm_provides,
                         path = rpm_path))

    return pkgs


def read_primary_sqlite(repo_path, primary_sqlite = os.path.join('repodata', 'primary.sqlite')):
    primary_sqlite = os.path.join(repo_path, primary_sqlite)
    primary_sqlite_tmp = None
    url = urlparse(primary_sqlite)

    if not primary_sqlite.endswith('.sqlite') or url.scheme not in [None, '', 'file']:
        primary_sqlite_tmp = mktemp()
        if url.scheme not in [None, '', 'file']:
            fd = urlopen(primary_sqlite)
        else:
            fd = open(primary_sqlite, 'rb')
        if primary_sqlite.endswith('.bz2'):
            with open(primary_sqlite_tmp, 'wb') as f:
                f.write(bz2_decompress(fd.read()))
        else:
            with open(primary_sqlite_tmp, 'wb') as f:
                f.write(fd.read())
        fd.close()

        primary_sqlite = primary_sqlite_tmp

    pkgdb = sqlite3.connect(primary_sqlite)
    cur = pkgdb.cursor()

    # Parse packages
    pkgs = set()
    cur.execute('SELECT name, version, release, arch, location_href, pkgKey FROM packages')
    for pkg in cur.fetchall():
        cur.execute('SELECT name FROM requires WHERE pkgKey=' + str(pkg[5]))
        req = set(r[0] for r in cur.fetchall())
        cur.execute('SELECT name FROM provides WHERE pkgKey=' + str(pkg[5]))
        prov = set(p[0] for p in cur.fetchall())
        pkgs.add(RpmInfo(name = pkg[0],
                         version = pkg[1],
                         release = pkg[2],
                         arch = pkg[3],
                         is_src = bool(pkg[3] == 'src'),
                         requires = req,
                         provides = prov,
                         path = pkg[4]))

    pkgdb.close()

    if primary_sqlite_tmp:
        os.remove(primary_sqlite_tmp)

    return pkgs
