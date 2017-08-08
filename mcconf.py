#!/usr/bin/python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(sys.argv[0]), "./python-libs"))
import pytoml as toml
from pathlib2 import Path
import logging
import argparse
import re
#import pydotplus.graphviz as pydot
import pydot
import shutil
import mako.template
import mako.runtime

def findFiles(basedir, patterns):
    """find files relative to a base directory according to a list of patterns.
    Returns a set of file names."""
    files = set()
    path = Path(basedir)
    for pattern in patterns:
        files.update([m.relative_to(basedir).as_posix() for m in path.glob(pattern)])
    return files



class ModFile:
    """represents a source to destination file mapping and is associated to its origin module.

    Attributes:
        module  the module this file belongs to, used for path resolution.
        srcname the path to the source file as given in the module definition,
                relative to the module file.
        srcfile the absolute path to the source file.
        dstfile the relative path to the destination file, relative to the target root.
        installMode how this file will be installed (link, hardlink, cinclude, copy).
    """

    def __init__(self, module, filename):
        self.installMode = 'link'
        self.module = module
        self.srcname = filename
        self.srcfile = os.path.join(self.module.moduledir, self.srcname)
        dstpath = os.path.join(self.module.dstdir, os.path.dirname(filename))
        dstname = os.path.basename(filename)
        if dstname.startswith("mako_"):
            self.installMode = 'mako'
            dstname = dstname[len("mako_"):]
        self.dstfile = os.path.join(dstpath, dstname)

    def __repr__(self): return self.dstfile

    @property
    def dependencies(self):
        """a list(string) with all C/C++ include dependencies"""
        incrgx = re.compile('^#include\\s+[<\\"]([\\w./-]+)[>\\"]', re.MULTILINE)
        # TODO detect the file type and choose a respective scanner instead
        # of handling all files as source files
        # TODO scan for special syntax that declares required and provided symbols for mcconf
        includes = list()
        srcdir = os.path.dirname(self.srcfile)
        try:
            with open(self.srcfile) as fin:
                for m in incrgx.finditer(fin.read()):
                    inc = m.group(1)
                    # if file is locally referenced e.g. 'foo' instead of 'path/to/foo'
                    # TODO this will break when we begin to rename files during composition
                    # ie. will have to check if moduledir/inc is one of the modules dstfiles
                    # would be better, to prohibit this per convention,
                    # ie "" always relative to sourcefile, <> always relative to the logical root
                    if os.path.exists(os.path.join(srcdir,inc)):
                        inc = os.path.relpath(os.path.join(srcdir,inc),
                                                  self.module.moduledir)
                    includes.append(inc)
        except Exception as e:
            logging.warning("could not load %s from %s: %s", fpath, self.modulefile, e)
        return includes

    def install(self, tgtdir, tmplenv):
        """install the file into the target directory."""
        srcfile = os.path.abspath(self.srcfile)
        tgtfile = os.path.abspath(os.path.join(tgtdir, self.dstfile))

        logging.debug('installing file %s to %s mode %s from module %s',
                          srcfile, tgtfile, self.installMode, self.module)
        if not os.path.isfile(srcfile):
            logging.warning('file %s is missing or not regular file, provided by %s from %s',
                            self.srcfile, self.module, self.module.modulefile)

        if not os.path.exists(os.path.dirname(tgtfile)):
            os.makedirs(os.path.dirname(tgtfile))
        # TODO ideally we should never overwrite files, reconfig run should delete previously installed files
        if os.path.exists(tgtfile) or os.path.islink(tgtfile):
            os.unlink(tgtfile)

        if self.installMode=='link':
            os.symlink(os.path.relpath(srcfile, os.path.dirname(tgtfile)), tgtfile)
        elif self.installMode=='hardlink':
            os.link(srcfile, tgtfile)
        elif self.installMode=='cinclude':
            with open(tgtfile, 'w') as f:
                f.write('#include "'+os.path.relpath(srcfile, tgtfile)+'"\n')
        elif self.installMode=='mako':
            with open(tgtfile, 'w') as f:
                tmpl = mako.template.Template(filename=self.srcfile)
                ctx = mako.runtime.Context(f, **tmplenv)
                tmpl.render_context(ctx)
        else: # copy the file
            shutil.copy2(srcfile, tgtfile)



class Module:
    """represents a code module as collection of source files and dependencies.

    Attributes:
        name       the name of the module as given in its definition.
        modulefile the path to the file containing this definition, relative to pwd.
        moduledir  the absolute path to the directory that contains the module,
                   used to resolve relative source files.
        dstdir     can be used to modify the destination path.
        files      a dictionary from role (e.g. incfiles, kernelfiles) to list(ModFile).
    """

    def __init__(self, name, modulefile):
        self.name = name
        self.modulefile = modulefile # TODO should be absolute in order to change pwd after scan ?!
        self.moduledir = os.path.dirname(os.path.abspath(self.modulefile))
        self.dstdir = ""
        self.files = dict()
        self._requires = set()
        self._provides = set()
        self.modules = set()
        self.copyfiles = set()
        self.vars = dict() # all unknown fields from the configuration
        self.providedFiles = set()
        self.requiredFiles = set()

    def __repr__(self): return self.name

    def addFiles(self, role, names):
        if role not in self.files: self.files[role] = list()
        self.files[role] += [ModFile(self, name) for name in names]

    @property
    def requires(self): return self._requires | self.requiredFiles
    def addRequires(self, s): self._requires.update(s)

    @property
    def provides(self): return self._provides | self.providedFiles
    def addProvides(self, s): self._provides.update(s)

    def finish(self):
        """finish the initialization of the module after all fields are set."""
        for role in self.files:
            for m in self.files[role]:
                self.providedFiles.add(m.dstfile)
                self.requiredFiles.update(m.dependencies)
                if m.srcname in self.copyfiles: m.installMode = 'copy'
        self.requiredFiles -= self.providedFiles


def parseTomlModule(modulefile):
    """parses a mcconf module file and returns a list(Module)."""
    modules = list()
    with open(modulefile, 'r') as f:
        content = toml.load(f)
        for name in content['module']:
            fields = content['module'][name]
            mod = Module(name, modulefile)
            for field in fields:
                if field.endswith('files'):
                    mod.addFiles(field.upper(), findFiles(mod.moduledir, fields[field]))
                elif field == 'copy': mod.copyfiles = set(fields['copy'])
                elif field == 'requires': mod.addRequires(fields['requires'])
                elif field == 'provides': mod.addProvides(fields['provides'])
                elif field == 'modules': mod.modules = set(fields['modules'])
                elif field == 'dstdir': mod.dstdir = fields['dstdir']
                else: mod.vars[field] = fields[field]
            #mod.provides.add(name) # should not require specific modules, use 'modules' instead
            mod.finish()
            modules.append(mod)
    return modules



class ModuleDB:
    """a collection of modules and dependency relationships."""
    def __init__(self):
        self.modules = dict()
        self.provides = dict()
        self.requires = dict()

    def addModule(self, mod):
        if mod.name not in self.modules:
            logging.debug('loaded %s from %s', mod.name, mod.modulefile)
            self.modules[mod.name] = mod
            for tag in mod.provides: # this tag is provided by that module
                if tag not in self.provides: self.provides[tag] = set()
                self.provides[tag].add(mod)
            for tag in mod.requires: # this tag is required by that module
                if tag not in self.requires: self.requires[tag] = set()
                self.requires[tag].add(mod)
        else:
            logging.warning('ignoring duplicate module %s from %s and %s',
                            mod.name, mod.modulefile,
                            self.modules[mod.name].filename)

    def __getitem__(self,index):
        return self.modules[index]

    def has(self, key):
        return key in self.modules

    def getProvides(self, tag):
        """Return a set of modules that provide this tag."""
        if tag not in self.provides:
            return set()
        return self.provides[tag]

    def isResolvable(self, mod, provided):
        """ Test whether there is a chance that the dependency are resolvable. """
        for req in mod.requires:
            if not (req in provided or len(self.getProvides(req))):
                logging.warning('Discarded module %s because of unresolvable dependency on %s', mod.name, req)
                return False
        return True

    def getResolvableProvides(self, tag, provided):
        return set([mod for mod in self.getProvides(tag) if self.isResolvable(mod, provided)])

    def getRequires(self, tag):
        """Return a set of modules that require this tag."""
        if tag not in self.requires:
            return set()
        return self.requires[tag]

    def getModules(self):
        return self.modules.values()

    def getSolutionCandidates(self, mod):
        """Find all modules that satisfy at least one dependency of the module.
        Returns a dictionary mapping modules to the tags they would satisfy."""
        dstmods = dict()
        for req in mod.requires:
            for dst in self.getProvides(req):
                if dst not in dstmods: dstmods[dst] = set()
                dstmods[dst].add(req)
        return dstmods

    def getConflictingModules(self, mod):
        """inefficient method to find all modules that are in conflict with the given one.
        Returns a dictionary mapping modules to the conflicting tags."""
        dstmods = dict()
        for prov in mod.provides:
            for dst in self.getProvides(prov):
                if dst.name == mod.name: continue
                if dst not in dstmods: dstmods[dst] = set()
                dstmods[dst].add(prov)
        return dstmods

    def checkConsistency(self):
        for mod in self.getModules():
            includes = mod.requiredFiles
            dups = mod.requires & includes # without required files!
            if dups:
                logging.warning('Module %s(%s) contains unnecessary requires: %s',
                                mod.name, mod.modulefile, str(dups))

        requires = set(self.requires.keys())
        provides = set(self.provides.keys())
        unsat = requires - provides
        if unsat != set():
            for require in unsat:
                names = [m.name+'('+m.modulefile+')' for m in self.getRequires(require)]
                logging.info('Tag %s required by %s not provided by any module',
                             require, str(names))


def loadModules(moddb, paths):
    for path in paths:
        for f in findFiles(path, ["**/*.module", "**/mcconf.toml", "**/*.mcconf"]):
            try:
                for mod in parseTomlModule(os.path.join(path,f)): moddb.addModule(mod)
            except:
                logging.error('parsing  modulefile %s failed', f)
                raise



def replaceSuffix(str, osuffix, nsuffix):
    return str[:-len(osuffix)] + nsuffix

class Configuration:
    def __init__(self, conffile):
        self.moduledirs = list()
        self.provides = set()
        self.requires = set()
        self.modules = set()
        self.dstdir = '.'

        self.acceptedMods = set() # set of selected module objects
        self.files = dict() # dict role -> dict dstfile -> ModFile
        self.allfiles = dict() # dict dstfile -> ModFile
        self.vars = {"config_file": os.path.abspath(conffile)}
        self.modDB = ModuleDB()

    def applyModules(self, pendingMods):
        '''add all modules of the list to the configuration, including referenced modules'''
        pendingMods = pendingMods.copy()
        while len(pendingMods) > 0:
            modname = pendingMods.pop()
            # 1) error if module not available
            if not self.modDB.has(modname):
                raise Exception("Didn't find module " + modname)
            # 2) ignore if module already selected
            mod = self.modDB[modname]
            if mod in self.acceptedMods: continue
            # 3) error if conflict with previously selected module
            # conflict if one of the provides is already provided
            conflicts = self.provides & mod.provides
            if conflicts:
                for tag in conflicts:
                    conflictMods = self.modDB.getProvides(tag) & self.acceptedMods
                    cnames = [m.name for m in conflictMods]
                    logging.warning("requested module %s tag %s conflicts with %s",
                                    mod.name, tag, str(cnames))
                    raise Exception("requested module " + modname +
                                    " conflicts with previously selected modules")
            # conflictMods = self.modDB.getConflictingModules(mod)
            # conflicts = conflictMods.keys() & self.acceptedMods
            # if conflicts:
            #     # TODO add more diagnostigs: which tags/files do conflict?
            #     cnames = [m.name for m in (conflicts|set(mod))]
            #     logging.warning("selected conflicting modules: "+cnames)

            logging.debug('selecting module %s', mod.name)
            self.acceptedMods.add(mod)
            pendingMods |= mod.modules
            self.requires |= mod.requires
            self.provides |= mod.provides
            for role in mod.files:
                for mf in mod.files[role]:
                    if mf.dstfile in self.allfiles:
                         logging.warning('duplicate file %s from module %s and %s',
                                         mf, mod. self.allfiles[mf.dstfile].module)
                    if role not in self.files: self.files[role] = dict()
                    self.files[role][mf.dstfile] = mf
                    self.allfiles[mf.dstfile] = mf

    def getMissingRequires(self):
        return self.requires - self.provides

    def processModules(self, resolveDeps):
        '''if resolveDeps is true, this method tries to resolve missing dependencies
        by including additional modules from the module DB'''
        self.applyModules(self.modules)

        if resolveDeps:
            additionalMods = self.resolveDependencies()
            names = ", ".join(sorted([m.name for m in additionalMods]))
            logging.info('added modules to resolve dependencies: %s', names)

        missingRequires = self.getMissingRequires()
        for tag in missingRequires:
            reqMods = self.modDB.getRequires(tag) & self.acceptedMods
            req = [m.name for m in reqMods]
            prov = [m.name for m in self.modDB.getProvides(tag)]
            logging.warning('unresolved dependency %s required by [%s] provided by [%s]',
                            tag, ', '.join(req), ', '.join(prov))

    def resolveDependencies(self):
        additionalMods = set()
        missingRequires = self.getMissingRequires()
        count = 1
        while count:
            count = 0
            for tag in missingRequires:
                solutions = self.modDB.getResolvableProvides(tag, self.provides).copy()
                # 1) ignore if none or multiple solutions
                if len(solutions) != 1: continue
                mod = solutions.pop()
                # 2) ignore if conflict with already selected modules
                conflicts = self.provides & mod.provides
                if conflicts: continue
                # select the module
                logging.debug('Satisfy dependency %s with module %s', tag, mod.name)
                additionalMods.add(mod)
                count += 1
                self.applyModules(set([mod.name]))
                missingRequires = self.getMissingRequires()
        # return set of additionally selected modules
        return additionalMods

    def checkConsistency(self):
        selected = set([self.modDB[n] for n in self.modules])
        removable = set()
        for mod in selected:
            # 1) modules with conflicts should be selected
            conflictMods = self.modDB.getConflictingModules(mod)
            if conflictMods: continue
            # 2) modules that do not satisfy any dependency should be selected
            providesAnything = False
            for tag in mod.provides:
                if self.modDB.getRequires(tag) & selected:
                    providesAnything = True
            if not providesAnything: continue
            # remember all other modules
            removable.add(mod)
        if removable:
            logging.info("following modules could be resolved automatically: %s",
                         str(removable))

    def install(self):
        tmplenv = {"vars": argparse.Namespace(**self.vars), "modules": self.acceptedMods,
                   "dstdir": os.path.abspath(self.dstdir),
                   "files": self.files, "allfiles":self.allfiles,
        }
        tmplenv['replaceSuffix'] = lambda str, osuf, nsuf: str[:-len(osuf)] + nsuf
        def tmplIncludeModules(var, ctx):
            for mod in ctx["modules"]:
                if var in mod.vars:
                    mako.template.Template(mod.vars[var]).render_context(ctx)
            return ''
        tmplenv['includeModules'] = tmplIncludeModules

        if not os.path.exists(self.dstdir): os.makedirs(self.dstdir)
        for k in self.allfiles: self.allfiles[k].install(self.dstdir, tmplenv)


def parseTomlConfiguration(conffile):
    with open(conffile, 'r') as fin:
        configf = toml.load(fin)
        configf = configf['config']
        config = Configuration(conffile)
        for field in configf:
            if field == 'vars': config.vars.update(configf[field])
            elif field == 'moduledirs': config.moduledirs = list(configf['moduledirs'])
            elif field == 'requires': config.requires.update(configf['requires'])
            elif field == 'provides': config.provides.update(configf['provides'])
            elif field == 'modules': config.modules.update(configf['modules'])
            elif field == 'destdir': config.dstdir = os.path.abspath(configf['destdir'])
        loadModules(config.modDB, config.moduledirs)
        return config



def createModulesGraph(moddb):
    graph = pydot.Dot(graph_type='digraph')
    nodes = dict()

    # add modules as nodes
    for mod in moddb.getModules():
        tt = ", ".join(mod.provides) + " "
        node = pydot.Node(mod.name, tooltip=tt)
        nodes[mod.name] = node
        graph.add_node(node)

    # add directed edges from modules to modules that satisfy at least one dependency
    for src in moddb.getModules():
        dstmods = moddb.getSolutionCandidates(src)
        for dst in dstmods:
            tt = ", ".join(dstmods[dst]) + " "
            edge = pydot.Edge(src.name, dst.name, tooltip=tt)
            graph.add_edge(edge)

    # add special directed edges for "modules" inclusion
    for src in moddb.getModules():
        for dstname in src.modules:
            dst = moddb[dstname]
            edge = pydot.Edge(src.name, dst.name, color="green")
            graph.add_edge(edge)

    # add undirected edges for conflicts
    for src in moddb.getModules():
        conflicts = moddb.getConflictingModules(src)
        for dst in conflicts:
            if (dst.name < src.name):
                tt = ", ".join(conflicts[dst]) + " "
                edge = pydot.Edge(src.name, dst.name, color="red", dir="none", tooltip=tt)
                graph.add_edge(edge)

    graph.write('dependencies.dot')


def createConfigurationGraph(modules, selectedmods, moddb, filename):
    graph = pydot.Dot(graph_name="G", graph_type='digraph')
    nodes = dict()

    # add modules as nodes
    for mod in modules:
        tt = ", ".join(mod.provides) + " "
        if mod.name in selectedmods:
            fc = "#BEF781"
        else:
            fc = "white"
        if moddb.getConflictingModules(mod):
            nc = "#DF0101"
        else:
            nc = "black"

        node = pydot.Node(mod.name, tooltip=tt,
                          style='filled', fillcolor=fc, color=nc, fontcolor=nc)
        # node = pydot.Node(mod.name)
        nodes[mod.name] = node
        graph.add_node(node)

    # add directed edges from modules to modules that satisfy at least one dependency
    for src in modules:
        dstmods = moddb.getSolutionCandidates(src)
        #print(str(src) + ' --> ' + str(dstmods))
        # don't show modules that are not in 'modules'
        for dst in dstmods:
            if dst not in modules: continue
            tt = ", ".join(dstmods[dst]) + " "
            edge = pydot.Edge(src.name, dst.name, tooltip=tt)
            # edge = pydot.Edge(src.name, dst.name)
            graph.add_edge(edge)

    # add special directed edges for "modules" inclusion
    for src in modules:
        for dstname in src.modules:
            dst = moddb[dstname]
            edge = pydot.Edge(src.name, dst.name, color="green")
            graph.add_edge(edge)

    graph.write(filename)



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', "--configfile", default = 'project.config')
    parser.add_argument('-d', "--destpath")
    parser.add_argument("--check", action = 'store_true')
    parser.add_argument('-v', "--verbose", action = 'store_true')
    parser.add_argument('-g', "--modulegraph", action = 'store_true')
    parser.add_argument("--nodepsolve", help = 'disables the solver', action = 'store_true')
    args = parser.parse_args()

    if args.destpath is not None:
        args.destpath = os.path.abspath(args.destpath)

    # configure the logging
    logFormatter = logging.Formatter("%(message)s")
    rootLogger = logging.getLogger()
    logfile = args.configfile+'.log'
    if os.path.exists(logfile): os.unlink(logfile)
    fileHandler = logging.FileHandler(logfile)
    fileHandler.setFormatter(logFormatter)
    fileHandler.setLevel(logging.DEBUG)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.setFormatter(logFormatter)
    if args.verbose:
        consoleHandler.setLevel(logging.DEBUG)
    else:
        consoleHandler.setLevel(logging.INFO)
    rootLogger.addHandler(consoleHandler)
    rootLogger.setLevel(logging.DEBUG)

    currentDir = os.getcwd()
    conffile = os.path.abspath(args.configfile)
    os.chdir(os.path.dirname(conffile))
    logging.info("processing configuration %s", args.configfile)
    config = parseTomlConfiguration(conffile)

    if args.destpath is not None:
        config.dstdir = args.destpath

    if(args.check):
        config.modDB.checkConsistency()
        config.checkConsistency()
    else:
        config.processModules(not args.nodepsolve)
        config.install()

    if args.modulegraph:
        createModulesGraph(config.modDB)
        createConfigurationGraph(config.acceptedMods, config.modules, config.modDB, config.dstdir+'/config.dot')

    sys.exit(0)
