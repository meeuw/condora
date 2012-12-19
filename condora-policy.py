import os

from conary.build import policy
from conary.deps import deps

class ParseRequires(policy.PackagePolicy):
    requires = (
        ('Requires', policy.REQUIRED),
    )
    processUnmodified = False

    def __init__(self, *args, **keywords):
	self.requiresfiles = {}
	policy.PackagePolicy.__init__(self, *args, **keywords)

    def updateArgs(self, *args, **keywords):
	if 'file' in keywords and 'package' in keywords:
            self.requiresfiles[keywords.pop('package')] = keywords.pop('file')
	policy.PackagePolicy.updateArgs(self, **keywords)

    def do(self):
        if len(self.requiresfiles) == 0: return
        for package, requiresfile in self.requiresfiles.iteritems():
            if not requiresfile.startswith('/'):
                requiresfile = self.macros['builddir'] + os.sep + requiresfile
            f = open(requiresfile)
            for line in f:
                for comp in self.recipe.autopkg.getComponents():
                    if comp.getName().startswith(package+':'):
                        comp.requires.addDep(deps.TroveDependencies, deps.Dependency(line.strip()))
            f.close()
