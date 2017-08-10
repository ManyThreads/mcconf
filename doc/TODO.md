# Tasks and Ideas for Improvement

## Convenience

* -Dsymbol command line arguments to add preprocessor definitions
* select additional modules via command line arguments
* Add a command line option do add additional moduledirs.

## Diagnostics

* highlight included modules of the configuration in the global dot graph 
* Find all cycles in the dependency graph and report these. Dependency
  cycles are an indicator for bad design and prevent reuse.

## Configuration Process

* add advanced automatic dependency resolution:
  * SAT solver: each module is modelled as a boolean variable (can be
    either used by the solution or not). The dependencies and
    conflicts are modelled through clauses. Let module m require x and
    x is provided by modules y1...yn, then add the clause "m => y1 or
    ... or y2". Let x be provided by more than one module y1...yn,
    then add a mutual exclusion clause for y1...yn.
	Might need formulation as LP-Problm, see:
	* http://0install.net/solver.html
	* https://github.com/enthought/depsolver and https://speakerdeck.com/cournape/depsolver-pycon-dot-fr
	* http://sahandsaba.com/understanding-sat-by-implementing-a-simple-sat-solver-in-python.html
	* https://pypi.python.org/pypi/PuLP
	* https://github.com/dokelung/msat
	* https://pypi.python.org/pypi/logilab-constraint/0.5.0
	* http://pyeda.readthedocs.org/en/latest/sudoku.html
	* https://pypi.python.org/pypi/pycosat
