#!/usr/bin/python
# Copyright 2013 Dick Marinus
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import shutil
import glob
import re

from conary.build import policy
from conary.deps import deps
from conary.lib import util

#class _RpmPolicy(policy.PackagePolicy):
class _RpmPolicy(policy.DestdirPolicy):
    def __init__(self, *args, **keywords):
        self.includes = []
        self.excludes = []
        #policy.PackagePolicy.__init__(self, *args, **keywords)
        policy.DestdirPolicy.__init__(self, *args, **keywords)

    def updateArgs(self, *args, **keywords):
        if 'includes' in keywords: self.includes.append(keywords.pop('includes'))
        if 'excludes' in keywords: self.excludes.append(keywords.pop('excludes'))
        #policy.PackagePolicy.updateArgs(self, **keywords)
        policy.DestdirPolicy.updateArgs(self, **keywords)
    def doRpm(self, recipe, queryformat, split='\n'):
        if not self.includes: return []
        rpmFileNames = []
        for include in self.includes:
            rpmFileNames += glob.glob(include%recipe.macros)
        for exclude in self.excludes:
            for rpmFileName in glob.glob(exclude%recipe.macros):
                rpmFileNames.remove(rpmFileName)
        return util.popen('rpm -qp --queryformat \'%s\' %s' % (queryformat, ' '.join(rpmFileNames))).read().split(split)
    
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
                elif reqs.endswith('-static'): reqs+=':devellib'
                elif reqs.endswith('-doc'): reqs+=':supdoc'
                else: reqs+=':runtime'
                if reqs:
                    reqs = re.escape(reqs)
                    print 'recipe.Requires', req, reqs
                    recipe.Requires(req, reqs)

class RpmFiles(_RpmPolicy):
    #bucket = policy.PACKAGE_CREATION
    processUnmodified = False
    requires = (
        ('Ownership', policy.REQUIRED),
        ('setModes', policy.REQUIRED),
        ('NormalizeManPages', policy.REQUIRED_SUBSEQUENT), # replaces files
        ('ComponentSpec', policy.REQUIRED_SUBSEQUENT),
        ('PackageSpec', policy.REQUIRED_SUBSEQUENT),
    )
    def doProcess(self, recipe):
        empty = True
        for files in self.doRpm(recipe, '[%{NAME} %{FILEMODES:octal} %{FILEUSERNAME} %{FILEGROUPNAME} %{FILENAMES}\\n]'):
            files_split = files.split(' ')
            for i in range(len(files_split)-1, 0, -1):
                if files_split[i] == '(none)': del files_split[i]
            if len(files_split) >= 5:
                empty = False
                name, perms, owner, group = files_split[:4]
                target = ' '.join(files_split[4:])
                recipe.setModes(int(perms, 0), util.literalRegex(target))
                if owner != 'root' or group != 'root': recipe.Ownership(owner, group, util.literalRegex(target))
                target = re.escape(target)
                print 'PackageSpec', name, target
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
        for querytag in ['POSTIN','PREUN','POSTUN','PREIN']:
            progs = self.doRpm(recipe, '%%{NAME} %%{VERSION} %%{RELEASE} %%{EPOCHNUM} %%{%sPROG}\\%%\\n' % querytag, '%\n')[:-1]
            scripts = self.doRpm(recipe, '%%{NAME} %%{VERSION} %%{RELEASE} %%{EPOCHNUM} %%{%s}\\%%\\n' % querytag, '%\n')[:-1]
            for progs, scripts in zip(progs, scripts):
                progs = progs.split(' ')
                if progs[4] == '(none)': continue
                scripts = scripts.split(' ')
                if scripts[4] == '(none)': scripts = scripts[:4]+['']
                name, version, release, epoch = progs[:4]
                progs = ' '.join(progs[4:])
                scripts = ' '.join(scripts[4:])
                if not name in m:
                    m[name] = ((name, version, release, epoch), {})
                m[name][1][rpm2conary[querytag]] = (progs, scripts)
        os.makedirs('%(destdir)s/%(taghandlerdir)s' % recipe.macros)
        os.makedirs('%(destdir)s/%(tagdescriptiondir)s' % recipe.macros)
        for name, value in m.iteritems():
            scripts = ''
            for case, script in value[1].iteritems():
                scripts += '''%s)
%s <(cat << 'EOFcondora'
%s
EOFcondora
)
;;
''' % (case, script[0], script[1])

            taghandlerfn = '/'.join((recipe.macros.taghandlerdir, name))
            with file(recipe.macros.destdir+taghandlerfn,'w') as f: f.write('''#!/usr/bin/bash
# %(EPOCH)s:%(NAME)s-%(VERSION)s.%(RELEASE)s
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
''' % {'NAME':value[0][0], 'VERSION':value[0][1], 'RELEASE':value[0][2], 'EPOCH':value[0][3], 'SCRIPTS':scripts})
            os.chmod(recipe.macros.destdir+taghandlerfn, 0755)
            recipe.PackageSpec(name, re.escape(taghandlerfn))
            tagdescriptionfn = '/'.join((recipe.macros.tagdescriptiondir, name))
            with file(recipe.macros.destdir+tagdescriptionfn,'w') as f:
                f.write('file\t%s/%s\ndatasource\tstdin\n' % (recipe.macros.taghandlerdir, name))
                for conaryaction in conaryactions:
                    f.write('implements\tfiles %s\n'%conaryaction)
                f.write('include\t%s/%s' % (recipe.macros.taghandlerdir, re.escape(name)))
            recipe.PackageSpec(name, re.escape(tagdescriptionfn))

class RpmUnhardlinkManPages(policy.DestdirPolicy):
    processUnmodified = False
    requires = (
        ('NormalizeManPages', policy.REQUIRED_SUBSEQUENT),
    )
    def doProcess(self, recipe):
        inodes = {}
        for dirpath, dirnames, filenames in os.walk('%(destdir)s/%(mandir)s'%recipe.macros):
            for filename in filenames:
                filename = '%s/%s'%(dirpath,filename)
                inode = os.lstat(filename).st_ino
                if inode in inodes:
                     os.remove(filename)
                     print 'os.symlink', (inodes[inode][len(recipe.macros.destdir)+1:], filename)
                     os.symlink(inodes[inode][len(recipe.macros.destdir)+1:], filename)
                else: inodes[inode] = filename

class RpmPackageSpecArtefact(policy.DestdirPolicy):
    bucket = policy.PACKAGE_CREATION
    processUnmodified = False
    requires = (
        ('PackageSpec', policy.REQUIRED_SUBSEQUENT),
        ('RpmScripts', policy.REQUIRED_PRIOR),
        ('RpmFiles', policy.REQUIRED_PRIOR),
    )
    def __init__(self, *args, **keywords):
        self.catchall = ''
        policy.DestdirPolicy.__init__(self, *args, **keywords)

    def updateArgs(self, *args, **keywords):
        if 'catchall' in keywords: self.catchall = keywords.pop('catchall')
        policy.DestdirPolicy.updateArgs(self, **keywords)
    def doProcess(self, recipe):
        if self.catchall: recipe.PackageSpec(self.catchall, '.*')

