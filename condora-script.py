import xml.dom.minidom
import urllib
import sqlite3
import bz2
import tempfile
import os
import os.path
import sys
import re
import subprocess
import sys
import optparse
import fileinput

repositories = {
    'fedora-17':{
        '/home/meeuw/condora/updates-primary.sqlite3':'http://mirror.nl.leaseweb.net/fedora/linux/updates/17/SRPMS/',
        '/home/meeuw/condora/release-primary.sqlite3':'http://mirror.nl.leaseweb.net/fedora/linux/releases/17/Fedora/source/SRPMS/',
    },
    'fedora-rawhide':{
        '/home/meeuw/condora/rawhide-source-primary.sqlite3':'http://mirrors.nl.eu.kernel.org/fedora/development/rawhide/source/SRPMS/',
        '/home/meeuw/condora/rawhide-x86_64-primary.sqlite3':'http://mirrors.nl.eu.kernel.org/fedora/development/rawhide/x86_64/os/',
    }
}

parser = optparse.OptionParser()
parser.add_option("--packages", dest="packages", help="file with packages")
parser.add_option("--source-packages", dest="sourcepackages", help="file with source packages")
parser.add_option("--repository", dest="repository", help="repository")
parser.add_option("--getdatabase", action="store_true", dest="get_database", help="get databases")
(options, args) = parser.parse_args()
primary = repositories[options.repository]
packages = []
if options.packages:
    with open(options.packages) as f:
        packages = re.split('[ \t\n]+', f.read())

if options.sourcepackages:
    with open(options.sourcepackages) as f:
        conn = sqlite3.connect('/home/meeuw/condora/rawhide-source-primary.sqlite3')
        c = conn.cursor()
        for sourcepackage in re.split('[ \t\n]+', f.read()):
            print sourcepackage
            if not sourcepackage: continue
            c.execute('select name from packages where location_href like ?', ('%%/%s%%'%sourcepackage,))
            packages.append(c.fetchone()[0])

def get_database(primary):
    for primary, mirror in primary.iteritems():
        repomdfilename = urllib.urlretrieve(mirror+'repodata/repomd.xml')[0]
        repomd = xml.dom.minidom.parse(repomdfilename)
        for element in repomd.getElementsByTagName('data'):
            if element.getAttribute('type') == 'primary_db':
                primary_db_bz2 = urllib.urlopen(mirror+element.getElementsByTagName('location').item(0).getAttribute('href')).read()
                break;

        with open(primary, 'w') as primary_db:
            primary_db.write(bz2.decompress(primary_db_bz2))

        os.remove(repomdfilename)

if options.get_database: get_database(primary)

conary_repository = 'crh.mrns.nl'
label = conary_repository + '@f:rh'

for arg in packages:
    for primary_db_filename in primary.iterkeys():
        if 'x86_64' in primary_db_filename: continue
        conn = sqlite3.connect(primary_db_filename)
        c = conn.cursor()
        c.execute('select name, version, release from packages where name like ?', [arg])
        row = c.fetchone()
        if row:
            m = re.match('(.*?)(\.fc[0-9]+)?$', row[2])
            print row[2]
            print m.groups()
            release = "'%s' + rpmDist" % m.group(1)
            rpmDist = m.group(2)
            if not rpmDist: rpmDist = ''
            if not os.path.exists(arg): subprocess.check_call("cvc newpkg --context=%s --factory=srpm %s=%s" % (conary_repository, arg, label), shell=True)
            clsname = row[0].replace('-', '')
            with open("%(name)s/%(name)s.py" % {'name':arg}, 'w') as f:
                recipe = '''class %(clsname)s(SRPMPackageRecipe):
    name = '%(name)s'
    version = '%(version)s'
    rpmDist = '%(rpmDist)s'
    rpmRelease = %(release)s
''' % {
                'clsname':clsname[0].upper()+clsname[1:],
                'name':row[0],
                'version': row[1],
                'rpmDist': rpmDist,
                'release': release
            }
                f.write(recipe)
            subprocess.call(["cvc", "add", arg+".py"], cwd=arg)
            not_committed = True
            buildRequiresMap = {}
            while not_committed:
                p = subprocess.Popen("cvc commit -m ''", shell=True, cwd=arg, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
                stdin, stderr = p.communicate('\n')
                if p.returncode == 0: not_committed = False
                print p.returncode, not_committed
                for line in stderr.splitlines():
                    if line.startswith('warning: user mockbuild does not exist - using root'): pass
                    elif line.startswith('warning: group mockbuild does not exist - using root'): pass
                    elif line.startswith('error: Build requirement'):
                        conn2 = sqlite3.connect('/home/meeuw/condora/rawhide-x86_64-primary.sqlite3')
                        c = conn2.cursor()
                        fail = line.split("'")[1][:-8]
                        c.execute('select packages.name from packages inner join provides on packages.pkgKey = provides.pkgKey where provides.name = ?', (fail,))
                        buildRequiresMap[fail] = str(c.fetchone()[0])
                        with open('%(name)s/%(name)s.py' % {'name':arg}, 'w') as f:
                            f.write(recipe+'    buildRequiresMap = %s\n'%str(buildRequiresMap))
                    else: print [line]
            break
        c.close()
        conn.close()
    
