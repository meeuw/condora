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
    def doRpm(self, recipe, args):
        if not self.includes: return
        rpmFileNames = []
        for include in self.includes:
            rpmFileNames += glob.glob(include%recipe.macros)
        for exclude in self.excludes:
            for rpmFileName in glob.glob(exclude%recipe.macros):
                rpmFileNames.remove(rpmFileName)
        ret = []
        for rpmFileName in rpmFileNames:
            ret += util.popen('%s %s' % (args, rpmFileName)).read().split('\n')
        return ret
    
class RpmRequires(_RpmPolicy):
    bucket = policy.PACKAGE_CREATION
    processUnmodified = False
    requires = (
        ('Requires', policy.REQUIRED_SUBSEQUENT),
    )
    def doProcess(self, recipe):
        for requires in self.doRpm(recipe, 'rpm -qp --queryformat \'[%{NAME},%{REQUIRES}\\n]\''):
            requires_split = requires.split(',')
            if len(requires_split) >= 2:
                req = requires_split[1]
                if '/' in req: continue #FIXME req = 'file: '+req
                elif '(' in req: continue #FIXME req = 'soname: '+req
                else: req = req+':runtime'
                recipe.Requires(req, requires_split[0]+':runtime')

class RpmFiles(_RpmPolicy):
    bucket = policy.PACKAGE_CREATION
    processUnmodified = False
    requires = (
        ('Ownership', policy.REQUIRED),
        ('setModes', policy.REQUIRED),
        ('PackageSpec', policy.REQUIRED_SUBSEQUENT),
    )
    def doProcess(self, recipe):
        for files in self.doRpm(recipe, 'rpm -qp --queryformat \'[%{NAME},0%{FILEMODES:octal},%{FILEUSERNAME},%{FILEGROUPNAME},%{FILENAMES}\\n]\''):
            files_split = files.split(',')
            if len(files_split) >= 5:
                name, perms, owner, group, target = files_split
                recipe.setModes(int(perms, 0), util.literalRegex(target))
                if owner != 'root' or group != 'root': recipe.Ownership(owner, group, util.literalRegex(target))
                recipe.PackageSpec(name, target)

class RpmScripts(_RpmPolicy):
    bucket = policy.PACKAGE_CREATION
    processUnmodified = False
    def doProcess(self, recipe):
        print self.doRpm('rpm -qp '+myrpmfilename+' --queryformat \'' \
                 '        update)\n        %%{POSTIN}\\n        %%{POSTINPROG}\\n        ;;\\n' \
                 '        preremove)\n        %%{PREUN}\\n        %%{PREUNPROG}\\n        ;;\\n' \
                 '        remove)\n        %%{POSTUN}\\n        %%{POSTUNPROG}\\n        ;;\\n' \
                 '        preupdate)\n        %%{PREIN}\\n        %%{PREINPROG}\\n        ;;\\n' \
                 '\'|grep -v \'^        (none)$\' >> %(destdir)s/%(taghandlerdir)s/'+package, package=package)
