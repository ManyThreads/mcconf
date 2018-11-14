#!/bin/sh

cd `dirname $0`

virtualenv env
. env/bin/activate

pip install pydot
pip install pydotplus
pip install toml
pip install mako
pip install argparse
pip install pyparsing
pip install pathlib2
