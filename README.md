# McConf: The Modular Compilation Configurator

McConf is a compile-time configuration management tool for extensible
software families. Requested target configurations are composed from
fine grained package descriptions by copying all needed source files
into the target directory. This approach is designed to enable compile-time
dependency injection: Modules can depend, for example, on particular
files and other modules can provide alternative implementations of
these files.

After composing the source, a Makefile is generated which can be used
to build the configured target. 

## Background

Traditional library-based software composition works by linking
previously compiled files and libraries into the target
executable. Dependencies between such libraries and configuration
options quickly lead to a large number of differently configured
library variants. In contrast, McConf jumps into action before
anything is compiled.

McConf has similar objectives as [cargo](http://doc.crates.io/) for the
rust language. However, McConf is targeted to C++ codes with a large
number of rather small modules, typically just a few source files.

## Using McConf

In order to generate a build configuration, supply mcconf with a
.config file. This tells mcconf where to find module descriptions and
which modules are desired. If nothing is specified, the file
project.config will be read.

	$MCDIR/mcconf -i myproj.config

A couple of additional flags are available for diagnostics:
* --check runs a sanity check accross the module descriptions and reports potential problems
* -v or --verbose activates verbose logging messages
* -g outputs the complete dependency graph as graphviz dot file

## Configuring your project variant

Configurations are described through files in the
[TOML format](https://github.com/toml-lang/toml). They contain a list
of search pathes to module descriptions, a list of system-provided
pseudo modules, and a list of requested modules. The configure tool
parses a given config filem, searches and parses all referenced module
files, and then copies the source files into the destination path
according to the description of requested modules.

~~~~
[config]
moduledirs = [ "../mythos", "../myapp", ...] # search pathes relative to position of the config file
destdir = "myworld" # destination path for the generated build configuration
provides = [ "x86", ...] # pseudo modules and so on that are assumed as available
requires = [ "gdtx86", "tlsx86", ...] # symbols etc that we require, for future dependency resolution
modules = [ ... ] # all modules that shall be included in this configuration
~~~~

## Adding own modules

Module descriptions are collected from all files that end in *.module
and lie in one of the configured search pathes. These files follow the
[TOML format](https://github.com/toml-lang/toml) and can descibe
multiple modules.

~~~~
[module.NAME]
srcfiles = [ "gdt-init.cc", ...] # all source files of the modules used during compilation
incfiles = [ "default-gdt.h", ...] # all exported header files, used during and after compilation
requires = [ "x86", ...] # symbols, files, pseudo modules required by this module
provides = [ "gdt", ...] # symbols and pseudo modules provided by this module. Files not needed because srcfiles and incfiles is added to the provides
modules  = [ ... ] # explicitly pulls other modules into the configuration, useful for meta-modules

[module.NAME2]
...
~~~~

Each module contains a name, various file lists, and dependency
metadata. All fields that end in "files" are recognised as file
list. The actual meaning of these lists depend on their use in the
generated makefiles. There, for each "foofiles" a variable "FOOFILES"
and "FOOFILES_OBJ" is inserted into the header of the makefile. The
referenced files are relative to the position of the module file and
will be placed accordingly relative to the destination directory. The
subdirectory structure is reproduced in the generated configuration
output.

The module dependencies are extracted almost automatically. All
referenced files are treated as "provides" and they are searched for
"#include" directives that result in "requires".  The "requires" and
"provides" fields can be used to add additional symbols and files if
they cannot be extracted automatically. For example, compiler modules
can provide system headers without copying these into the source code.

The "modules" field can be used to directly include other
modules. This can be used to define meta-modules that describe a
specific configuration of a whole subsystem. However, looking forward
to dependency-driven automatic selection of modules, the role of this
feature is questionable. As a rule of thumb, never mix files and
"modules" fields in a module. Do not add manual requirements that are
a requirement of a included module already.

### Makefile related extensions

The generated makefile is structured into following parts
* file list variables: these are generated from the union of "files"
  fields
* "makefile_head" strings from all used modules in an arbitrary order
* the "all: $(TARGETS)" rule
* "makefile_body" strings from all used modules in an arbitrary order
* generated clean and make dependency rules

~~~~
[module.NAME]
...
makefile_head = '''
        add variable definitions here
'''
makefile_body = '''
        add make rule definitions here
'''		
~~~~

### Modules as configuration helpers

The field `noauto = true` can be used to prevent automatic selection of the module during dependency resolution.
Such modules are useful to provide a set of platform and architecture specific pseudo-symbols (aka tags) in order
to be reused across multiple configurations.
Without `noauto`, our simple dependency resolution fails with ambiguous resolution candidates.
This is caused because it would consider all candidate modules just because one of these configuration
helper modules could in theory satisfy the needed acrhitecture or platform dependency.


## Details of the Configuration Process

* first, the module search path is processed for module files and all are parsed. The configuration tool should check for duplicate module names and report respective warnings. The path to the module file is added to the in-memory module description in order to find the referenced files later.
* the requested modules descriptions are combined into lists of source and include files with pairs of source and target path. The requires and provides are combined as well. The configuration tool checks for duplicate files and provided pseudo modules and report respective warnings.
* after all modules are combined, the list of still required modules and pseudo modules should be empty. Otherwise, a warning should be reported for each missing module, including a list of suggested modules that would satisfy this dependency.
* the include and source files are copied to the configuration destination using symbolic links and the intermediate directories are created as needed.
* finally, a makefile is generated based on generic make rules and a list of kernel object files. the 
kernel object files are retrieved by taking all *.S and *.cc source files and replacing the suffix with *.o.

# Acknowledgements

McConf was initially developed as part of the MyThOS project. It was funded by the Federal Ministry of Education and Research (BMBF) under Grant No. 01IH13003 from October 2013 to September 2016.
