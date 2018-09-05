#!/bin/bash

pushd `dirname $0` > /dev/null

virtualenv env
source env/bin/activate

#pip install --upgrade pip
pip install pydot
pip install pydotplus
pip install pytoml==0.1.2
pip install mako
pip install argparse
pip install pyparsing
pip install pathlib2

popd > /dev/null
