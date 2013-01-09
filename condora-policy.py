import os
import shutil
import glob
import re

from conary.build import policy
from conary.deps import deps
from conary.lib import util

class _RpmPolicy(policy.PackagePolicy):
    def __init__(self, *args, **keywords):
	self.includes = []
	self.excludes = []
	policy.PackagePolicy.__init__(self, *args, **keywords)

    def updateArgs(self, *args, **keywords):
	if 'includes' in keywords: self.includes.append(keywords.pop('includes'))
	if 'excludes' in keywords: self.excludes.append(keywords.pop('excludes'))
	policy.PackagePolicy.updateArgs(self, **keywords)
    def doRpm(self, recipe, queryformat):
        if not self.includes: return
        rpmFileNames = []
        for include in self.includes:
            rpmFileNames += glob.glob(include%recipe.macros)
        for exclude in self.excludes:
            for rpmFileName in glob.glob(exclude%recipe.macros):
                rpmFileNames.remove(rpmFileName)
        ret = []
        for rpmFileName in rpmFileNames:
            ret += util.popen('rpm -qp --queryformat \'%s\' %s' % (queryformat, rpmFileName)).read().split('\n')
        return ret
    
class RpmRequires(_RpmPolicy):
    bucket = policy.PACKAGE_CREATION
    processUnmodified = False
    requires = (
        ('ComponentSpec', policy.REQUIRED_PRIOR),
        ('PackageSpec', policy.REQUIRED_PRIOR),
        ('Requires', policy.REQUIRED_SUBSEQUENT),
    )
    def __init__(self, *args, **keywords):
        self.requiresMap = {}
        _RpmPolicy.__init__(self, *args, **keywords)
    def updateArgs(self, *args, **keywords):
	if 'requiresMap' in keywords: self.requiresMap = keywords.pop('requiresMap')
        _RpmPolicy.updateArgs(self, **keywords)
    def doProcess(self, recipe):
        for requires in self.doRpm(recipe, '[%{NAME},%{REQUIRES}\\n]'):
            requires_split = requires.split(',')
            if len(requires_split) >= 2:
                req = requires_split[1]
                if '/' in req: continue #FIXME req = 'file: '+req
                elif '(' in req: continue #FIXME req = 'soname: '+req
                else: req+=':runtime'
                reqs = requires_split[0]
                if reqs in self.requiresMap: reqs=self.requiresMap[reqs]
                elif reqs.endswith('-devel'): reqs+=':devel'
                elif reqs.endswith('-python'): reqs+=':python'
                elif reqs.endswith('-libs-static'): reqs+=':devellib'
                elif reqs.endswith('-doc'): reqs+=':supdoc'
                else: reqs+=':runtime'
                if reqs: recipe.Requires(req, reqs)

class RpmFiles(_RpmPolicy):
    bucket = policy.PACKAGE_CREATION
    processUnmodified = False
    requires = (
        ('Ownership', policy.REQUIRED),
        ('setModes', policy.REQUIRED),
        ('ComponentSpec', policy.REQUIRED_SUBSEQUENT),
        ('PackageSpec', policy.REQUIRED_SUBSEQUENT),
    )
    def doProcess(self, recipe):
        empty = True
        for files in self.doRpm(recipe, '[%{NAME},%{FILEMODES:octal},%{FILEUSERNAME},%{FILEGROUPNAME},%{FILENAMES}\\n]'):
            files_split = files.split(',')
            for i in range(len(files_split)-1, 0, -1):
                if files_split[i] == '(none)': del files_split[i]
            if len(files_split) >= 5:
                empty = False
                name, perms, owner, group, target = files_split
                recipe.setModes(int(perms, 0), util.literalRegex(target))
                if owner != 'root' or group != 'root': recipe.Ownership(owner, group, util.literalRegex(target))
                target = re.escape(target)
                recipe.PackageSpec(name, target)
        if empty:
            os.makedirs('%(destdir)s/etc/condora/'%self.recipe.macros)
            with open('%(destdir)s/etc/condora/%(name)s'%self.recipe.macros,'w') as f: f.write('')

class RpmScripts(_RpmPolicy):
    bucket = policy.PACKAGE_CREATION
    processUnmodified = False
    requires = (
        ('PackageSpec', policy.REQUIRED_SUBSEQUENT),
    )
    def doProcess(self, recipe):
        m = {}
        rpm2conary = {'POSTIN':'update','PREUN':'preremove','POSTUN':'remove','PREIN':'preupdate'}
        conaryactions = []
        for querytag in ['POSTIN','POSTINPROG','PREUN','PREUNPROG','POSTUN','POSTUNPROG','PREIN','PREINPROG']:
            ret = self.doRpm(recipe, '%%{NAME}\n%%{VERSION}\n%%{RELEASE}\n%%{%s}' % querytag)
            if '(none)' in ret: ret.remove('(none)')
            name, version, release = ret[:3]
            ret = ret[3:]
            if not name in m: m[name] = {'NAME':name,'VERSION':version,'RELEASE':release}
            if not 'SCRIPTS' in m[name]: m[name]['SCRIPTS'] = ''
            if ret:
                for rpm, conary in rpm2conary.iteritems():
                    if querytag.startswith(rpm): break
                conaryactions.append(conary)
                m[name]['SCRIPTS'] += '''%s)
%s
;;''' % (conary, '\n'.join(ret))
        if conaryactions:
            for name, scripts in m.iteritems():
                os.makedirs('%(destdir)s/%(taghandlerdir)s' % recipe.macros)
                taghandlerfn = ('%(destdir)s/%(taghandlerdir)s/' % recipe.macros) + name
                with file(taghandlerfn,'w') as f: f.write('''#!/bin/bash
# %(NAME)s-%(VERSION)s.%(RELEASE)s
if [ $# -lt 2 ]; then
    echo "not enough arguments: $0 $*" >&2
    exit 1
fi

type="$1"
shift
action="$1"
shift
case $type in
    files)
        case $action in
%(SCRIPTS)s
        esac
    ;;
esac
''' % scripts)
                os.chmod(taghandlerfn, 0755)
                recipe.PackageSpec(name, taghandlerfn)
                tagdescriptionfn = ('%(destdir)s/%(tagdescriptiondir)s/' % recipe.macros) + name
                os.makedirs('%(destdir)s/%(tagdescriptiondir)s' % recipe.macros)
                with file(tagdescriptionfn,'w') as f:
                    f.write('file\t%s/%s\ndatasource\tstdin\n' % (recipe.macros.taghandlerdir, name))
                    for conaryaction in conaryactions:
                        f.write('implements\tfiles %s\n'%conaryaction)
                    f.write('include\t%s/%s' % (recipe.macros.taghandlerdir, name))
                recipe.PackageSpec(name, tagdescriptionfn)

class RpmUnhardlinkManPages(policy.DestdirPolicy):
    processUnmodified = False
    requires = (
        ('NormalizeManPages', policy.REQUIRED_SUBSEQUENT),
    )
    def doProcess(self, recipe):
        return
        inodes = {}
        for dirpath, dirnames, filenames in os.walk('%(destdir)s/%(mandir)s'%recipe.macros):
            for filename in filenames:
                filename = '%s/%s'%(dirpath,filename)
                inode = os.stat(filename).st_ino
                if inode in inodes:
                     os.remove(filename)
                     print 'os.symlink', (inodes[inode][len(recipe.macros.destdir)+1:], filename)
                     os.symlink(inodes[inode][len(recipe.macros.destdir)+1:], filename)
                else: inodes[inode] = filename
