#!/bin/bash
vr=$(git describe --tags --long)
echo -n "__version__='" >version.py
echo -n $vr >>version.py
echo "'" >>version.py