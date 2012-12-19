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

primary = {
    '/home/meeuw/condora/updates-primary.sqlite3':'http://mirror.nl.leaseweb.net/fedora/linux/updates/17/SRPMS/',
    '/home/meeuw/condora/release-primary.sqlite3':'http://mirror.nl.leaseweb.net/fedora/linux/releases/17/Fedora/source/SRPMS/',
}

primary = {
    '/home/meeuw/condora/rawhide-updates-primary.sqlite3':'http://mirrors.nl.eu.kernel.org/fedora/development/rawhide/source/SRPMS/',
}

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

#get_database(primary)

for arg in sys.argv[1:]:
    for primary_db_filename in primary.iterkeys():
        conn = sqlite3.connect(primary_db_filename)
        c = conn.cursor()
        c.execute('select name, version, release from packages where name like ?', [arg])
        row = c.fetchone()
        if row:
            m = re.match('(.*)(\.fc12|\.fc15|\.fc16|\.fc17|\.fc18|\.fc19)(.*)', row[2])
            print row[2]
            print m.groups()
            if m.group(3): release = "'%s' + rpmDist + '%s'" % (m.group(1), m.group(3))
            else: release = "'%s' + rpmDist" % m.group(1)
            subprocess.check_call("cvc newpkg --context condora.mrns.nl --factory=srpm %s=condora.mrns.nl@f:rawhide" % arg, shell=True)
#            subprocess.check_call("cvc co --context condora.mrns.nl %s=condora.mrns.nl@f:16" % arg, shell=True)
            with open("%(name)s/%(name)s.py" % {'name':arg}, 'w') as f:
                f.write('''class %(clsname)s(SRPMPackageRecipe):
    name = '%(name)s'
    version = '%(version)s'
    rpmDist = '%(rpmDist)s'
    rpmRelease = %(release)s
''' % {
                'clsname':row[0][0].upper()+row[0][1:],
                'name':row[0],
                'version': row[1],
                'rpmDist': m.group(2),
                'release': release
            })
            subprocess.check_call("cd %(name)s ; cvc add %(name)s.py" % {'name':arg}, shell=True)
            subprocess.check_call("cd %(name)s ; cvc commit -m ''" % {'name':arg}, shell=True)
            break
        c.close()
        conn.close()
    
