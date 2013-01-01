import os
import glob

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
    def doProcess(self, recipe):
        for requires in self.doRpm(recipe, '[%{NAME},%{REQUIRES}\\n]'):
            requires_split = requires.split(',')
            if len(requires_split) >= 2:
                req = requires_split[1]
                if '/' in req: continue #FIXME req = 'file: '+req
                elif '(' in req: continue #FIXME req = 'soname: '+req
                else: req+=':runtime'
                reqs = requires_split[0]
                if reqs.endswith('-devel'): reqs+=':devel'
                else: reqs+=':runtime'
                recipe.Requires(req, reqs)

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
        for files in self.doRpm(recipe, '[%{NAME},0%{FILEMODES:octal},%{FILEUSERNAME},%{FILEGROUPNAME},%{FILENAMES}\\n]'):
            files_split = files.split(',')
            if len(files_split) >= 5:
                name, perms, owner, group, target = files_split
                recipe.setModes(int(perms, 0), util.literalRegex(target))
                if owner != 'root' or group != 'root': recipe.Ownership(owner, group, util.literalRegex(target))
                recipe.PackageSpec(name, target)

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
