#!/bin/bash

pushd `dirname $0` > /dev/null

virtualenv env
source env/bin/activate

pip install pydot
pip install pydotplus
pip install toml
pip install mako
pip install argparse
pip install pyparsing
pip install pathlib2

popd > /dev/null
